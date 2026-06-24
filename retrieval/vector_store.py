"""TF-IDF backed retriever over the Acme SaaS knowledge base.

Implementation note: we deliberately use TF-IDF + cosine similarity instead of an
external embeddings provider so the demo is fully reproducible without API keys.
The interface mirrors what a swappable embedding store would expose, so a future
swap to Chroma/pgvector is mechanical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import KB_DIR, RETRIEVAL_TOP_K


@dataclass
class KBChunk:
    source: str
    section: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.source}#{self.section}"


_HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def _split_markdown(path: Path) -> List[KBChunk]:
    raw = path.read_text(encoding="utf-8")
    parts = _HEADING.split(raw)
    chunks: List[KBChunk] = []
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


class VectorStore:
    """TF-IDF index over markdown KB chunks."""

    def __init__(self, chunks: List[KBChunk]):
        if not chunks:
            raise ValueError("VectorStore requires at least one KB chunk.")
        self.chunks = chunks
        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
        )
        self._matrix = self._vectorizer.fit_transform(c.text for c in chunks)

    def search(
        self, query: str, top_k: int = RETRIEVAL_TOP_K, min_score: float = 0.08
    ) -> List[tuple[KBChunk, float]]:
        """Return up to top_k (chunk, score) tuples sorted by descending score.

        Chunks scoring below ``min_score`` are filtered out so the retriever can
        truthfully say "no grounded evidence" when nothing matches.
        """
        if not query.strip():
            return []
        q_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self._matrix).flatten()
        # argsort returns ascending, so reverse and slice.
        ranked = np.argsort(sims)[::-1][:top_k]
        results: List[tuple[KBChunk, float]] = []
        for idx in ranked:
            score = float(sims[idx])
            if score < min_score:
                continue
            results.append((self.chunks[idx], score))
        return results


_singleton: Optional[VectorStore] = None


def get_vector_store(kb_dir: Path = KB_DIR) -> VectorStore:
    """Return a process-wide singleton VectorStore."""
    global _singleton
    if _singleton is not None:
        return _singleton
    chunks: List[KBChunk] = []
    for md_path in sorted(kb_dir.glob("*.md")):
        chunks.extend(_split_markdown(md_path))
    _singleton = VectorStore(chunks)
    return _singleton
