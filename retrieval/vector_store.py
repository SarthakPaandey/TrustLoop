"""Hybrid retriever over the Acme SaaS knowledge base.

Two complementary lexical signals are fused per query:

1. TF-IDF + cosine similarity (scikit-learn) — precise on exact terminology.
2. BM25 (implemented inline, zero extra dependencies) — robust on rare terms
   and short queries where raw cosine under-scores.

Fusion model:
    candidates = union(top-K_tfidf, top-K_bm25)
    hybrid     = w * tfidf_cosine + (1 - w) * bm25_relative
where ``bm25_relative`` is the BM25 score divided by the best BM25 score in the
candidate set, so both signals live on a comparable [0, 1] scale.

The interface mirrors what a swappable embedding store would expose, so a future
swap to Chroma/pgvector remains mechanical. When no signal clears its noise
floor the retriever returns an empty list, preserving the "no grounded evidence"
contract that the verifier relies on.

Live documents: ``ingest_document`` saves a ``.md``/``.txt`` file into the KB
directory and rebuilds the index, so uploads via the UI or API are searchable
immediately — no restart required.
"""

from __future__ import annotations

import math
import re
import threading
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import HYBRID_TFIDF_WEIGHT, KB_DIR, RETRIEVAL_TOP_K


class KBChunk:
    """A single retrieval chunk from the knowledge base.

    Plain class (not @dataclass) for Python 3.14 + Streamlit Cloud compatibility:
    dataclass field inspection can fail while the module is still loading.
    """

    __slots__ = ("section", "source", "text")

    def __init__(self, source: str, section: str, text: str) -> None:
        self.source = source
        self.section = section
        self.text = text

    @property
    def citation(self) -> str:
        return f"{self.source}#{self.section}"

    def __repr__(self) -> str:
        return f"KBChunk(source={self.source!r}, section={self.section!r})"


_HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)
_TOKEN = re.compile(r"[a-z0-9]+")


def _split_markdown(path: Path) -> list[KBChunk]:
    raw = path.read_text(encoding="utf-8")
    parts = _HEADING.split(raw)
    chunks: list[KBChunk] = []
    # First element before any "## " heading is the preamble (with the H1 title).
    preamble = parts[0].strip()
    if preamble:
        chunks.append(
            KBChunk(source=path.name, section="overview", text=preamble)
        )
    # Remaining elements alternate: heading, body, heading, body, ...
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            chunks.append(
                KBChunk(
                    source=path.name,
                    section=heading.lower().replace(" ", "_"),
                    text=f"{heading}\n{body}",
                )
            )
    return chunks


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens minus sklearn's English stopword set.

    Shared by the BM25 scorer and any future embedding-free rerankers so every
    lexical stage sees identical token streams.
    """
    return [
        t for t in _TOKEN.findall(text.lower()) if t not in ENGLISH_STOP_WORDS
    ]


class _BM25:
    """Okapi BM25 (k1=1.5, b=0.75) over pre-tokenized documents."""

    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = len(docs_tokens)
        self.doc_len = [len(d) for d in docs_tokens]
        self.avgdl = (sum(self.doc_len) / self.doc_count) if self.doc_count else 0.0
        self.tf: list[dict[str, int]] = [{} for _ in docs_tokens]
        df: dict[str, int] = {}
        for i, tokens in enumerate(docs_tokens):
            counts: dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1
            self.tf[i] = counts
            for t in counts:
                df[t] = df.get(t, 0) + 1
        # IDF uses the standard BM25+ variant floored at epsilon to avoid
        # negative weights for ubiquitous terms.
        self.idf: dict[str, float] = {
            t: math.log(1.0 + (self.doc_count - n + 0.5) / (n + 0.5))
            for t, n in df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = [0.0] * self.doc_count
        if not query_tokens or not self.avgdl:
            return out
        for term in query_tokens:
            idf = self.idf.get(term)
            if not idf:
                continue
            for i in range(self.doc_count):
                freq = self.tf[i].get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (
                    1.0 - self.b + self.b * self.doc_len[i] / self.avgdl
                )
                out[i] += idf * (freq * (self.k1 + 1.0)) / denom
        return out


class VectorStore:
    """Hybrid TF-IDF + BM25 index over markdown KB chunks."""

    def __init__(self, chunks: list[KBChunk]):
        if not chunks:
            raise ValueError("VectorStore requires at least one KB chunk.")
        self.chunks = chunks
        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
        )
        self._matrix = self._vectorizer.fit_transform(c.text for c in chunks)
        self._bm25 = _BM25([tokenize(c.text) for c in chunks])

    def search(
        self,
        query: str,
        top_k: int = RETRIEVAL_TOP_K,
        min_score: float | None = None,
    ) -> list[tuple[KBChunk, float]]:
        """Return up to top_k (chunk, fused_score) tuples, best first.

        ``min_score`` filters weak matches on the fused scale so the retriever
        can truthfully say "no grounded evidence" when nothing matches.
        """
        from config import RETRIEVAL_MIN_SCORE

        cutoff = RETRIEVAL_MIN_SCORE if min_score is None else min_score
        if not query.strip():
            return []

        q_vec = self._vectorizer.transform([query])
        tfidf_scores = {}
        sims = cosine_similarity(q_vec, self._matrix).flatten()
        for idx, s in enumerate(sims):
            if s > 0:
                tfidf_scores[idx] = float(s)

        q_tokens = tokenize(query)
        bm25_raw = self._bm25.scores(q_tokens)
        bm25_scores = {}
        max_bm25 = max(bm25_raw) if bm25_raw else 0.0
        if max_bm25 > 0:
            for idx, s in enumerate(bm25_raw):
                if s > 0:
                    bm25_scores[idx] = s / max_bm25

        candidates = set(tfidf_scores) | set(bm25_scores)
        if not candidates:
            return []
        max_tfidf = max(tfidf_scores.values()) if tfidf_scores else 0.0

        scored: list[tuple[float, int]] = []
        for idx in candidates:
            t_rel = (
                tfidf_scores[idx] / max_tfidf if max_tfidf > 0 and idx in tfidf_scores else 0.0
            )
            b_rel = bm25_scores.get(idx, 0.0)
            hybrid = HYBRID_TFIDF_WEIGHT * t_rel + (1 - HYBRID_TFIDF_WEIGHT) * b_rel
            # Noise floors: at least one system must see genuine signal.
            if hybrid >= cutoff and (
                tfidf_scores.get(idx, 0.0) >= 0.05 or b_rel >= 0.15
            ):
                scored.append((hybrid, idx))

        scored.sort(reverse=True)
        results: list[tuple[KBChunk, float]] = []
        seen: set[int] = set()
        for score, idx in scored[:top_k]:
            if idx in seen:
                continue
            seen.add(idx)
            results.append((self.chunks[idx], round(score, 4)))
        return results


_singleton: VectorStore | None = None
_singleton_lock = threading.Lock()
_singleton_kb_dir: Path | None = None


def _iter_doc_paths(kb_dir: Path) -> list[Path]:
    """KB source files in deterministic order (markdown + plain text)."""
    return sorted(kb_dir.glob("*.md")) + sorted(kb_dir.glob("*.txt"))


def get_vector_store(kb_dir: Path | None = None) -> VectorStore:
    """Return a process-wide singleton VectorStore (thread-safe).

    Rebuilt if a different ``kb_dir`` is requested (tests / tooling). The
    default resolves ``KB_DIR`` at call time so overrides take effect.
    """
    kb_dir = KB_DIR if kb_dir is None else kb_dir
    global _singleton, _singleton_kb_dir
    with _singleton_lock:
        if _singleton is not None and _singleton_kb_dir == kb_dir:
            return _singleton
        chunks: list[KBChunk] = []
        for doc_path in _iter_doc_paths(kb_dir):
            chunks.extend(_split_markdown(doc_path))
        _singleton = VectorStore(chunks)
        _singleton_kb_dir = kb_dir
        return _singleton


def reset_vector_store() -> None:
    """Clear the singleton (tests / KB reload)."""
    global _singleton, _singleton_kb_dir
    with _singleton_lock:
        _singleton = None
        _singleton_kb_dir = None


# ---- Live document ingestion ----

ALLOWED_DOC_SUFFIXES = (".md", ".txt")
MAX_DOC_CHARS = 200_000
MAX_DOCS = 200


def _sanitize_doc_name(filename: str) -> str:
    """Return a safe basename for a KB file, rejecting traversal and odd types.

    ``Path(filename).name`` drops any directory components, so ``../evil.md``
    collapses to ``evil.md`` inside the KB dir — it can never escape it.
    """
    name = Path(filename).name.strip()
    if not name or name.startswith("."):
        raise ValueError(f"Invalid document filename: {filename!r}.")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_DOC_SUFFIXES:
        raise ValueError(
            f"Unsupported document type {suffix or '(none)'} — use .md or .txt."
        )
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).stem).strip("._") or "document"
    return f"{stem[:80]}{suffix}"


def list_documents(kb_dir: Path | None = None) -> list[dict]:
    """Inventory of live KB source files with chunk counts."""
    kb_dir = KB_DIR if kb_dir is None else kb_dir
    docs = []
    for path in _iter_doc_paths(kb_dir):
        try:
            chunks = _split_markdown(path)
        except OSError:
            continue
        docs.append(
            {
                "filename": path.name,
                "chunks": len(chunks),
                "chars": path.stat().st_size,
            }
        )
    return docs


def ingest_document(
    filename: str, content: str, kb_dir: Path | None = None
) -> dict:
    """Save a document into the KB and rebuild the RAG index immediately.

    Overwrites when ``filename`` already exists (document update). Returns a
    summary dict with the stored name, chunk counts, and index totals. Raises
    ``ValueError`` on empty/oversized content, bad filenames, or a full KB.
    """
    kb_dir = KB_DIR if kb_dir is None else kb_dir
    if not content or not content.strip():
        raise ValueError("Document content cannot be empty.")
    if len(content) > MAX_DOC_CHARS:
        raise ValueError(
            f"Document exceeds {MAX_DOC_CHARS:,} characters "
            f"(got {len(content):,})."
        )
    safe = _sanitize_doc_name(filename)
    kb_dir.mkdir(parents=True, exist_ok=True)
    target = kb_dir / safe
    created = not target.exists()
    if created and len(_iter_doc_paths(kb_dir)) >= MAX_DOCS:
        raise ValueError(f"Knowledge base is full (max {MAX_DOCS} documents).")
    target.write_text(content, encoding="utf-8")
    chunks = _split_markdown(target)
    reset_vector_store()
    store = get_vector_store(kb_dir)
    return {
        "filename": safe,
        "created": created,
        "chunks": len(chunks),
        "total_documents": len(_iter_doc_paths(kb_dir)),
        "total_chunks": len(store.chunks),
    }


def find_chunk_by_citation(citation: str) -> KBChunk | None:
    """Resolve a `filename#section` citation back to its chunk, if indexed."""
    store = get_vector_store()
    for chunk in store.chunks:
        if chunk.citation == citation:
            return chunk
    return None
