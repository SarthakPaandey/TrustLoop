"""Tests for live knowledge-base ingestion: upload a document at runtime and
the RAG index picks it up immediately — no restart required."""

from __future__ import annotations

import pytest

import retrieval.vector_store as vs
from retrieval import (
    get_vector_store,
    ingest_document,
    list_documents,
    reset_vector_store,
)


@pytest.fixture()
def live_kb(tmp_path):
    """Isolated KB dir with one seed doc; singleton restored afterwards."""
    (tmp_path / "seed.md").write_text(
        "# Seed Policy\n\n## Overview\n\nSeed content about office plants.\n",
        encoding="utf-8",
    )
    reset_vector_store()
    yield tmp_path
    reset_vector_store()


class TestIngest:
    def test_uploaded_doc_is_searchable_immediately(self, live_kb):
        info = ingest_document(
            "vpn_policy.md",
            "# VPN Policy\n\n## Remote Access\n\nAll remote access must use "
            "WireGuard VPN with hardware keys.\n",
            kb_dir=live_kb,
        )
        assert info["created"] is True
        assert info["filename"] == "vpn_policy.md"
        assert info["chunks"] >= 1
        hits = get_vector_store(live_kb).search("WireGuard remote access VPN")
        assert hits
        assert hits[0][0].source == "vpn_policy.md"

    def test_reupload_updates_in_place(self, live_kb):
        first = ingest_document("notes.txt", "Initial words about zebras.", kb_dir=live_kb)
        second = ingest_document("notes.txt", "Revised words about zebras.", kb_dir=live_kb)
        assert first["created"] is True
        assert second["created"] is False
        assert second["filename"] == "notes.txt"

    def test_researcher_cites_live_doc(self, live_kb, monkeypatch):
        monkeypatch.setattr(vs, "KB_DIR", live_kb)
        reset_vector_store()
        ingest_document(
            "badge_policy.md",
            "# Badge Policy\n\n## Entry\n\nServer room entry requires a "
            "blue badge plus manager approval.\n",
        )
        from agents import parse_questionnaire, research_answer

        q = parse_questionnaire("What is required for server room entry?")[0]
        answer = research_answer(q)
        assert any("badge_policy.md" in cite for cite in answer.evidence)

    def test_rejects_bad_type(self, live_kb):
        with pytest.raises(ValueError, match="nsupported"):
            ingest_document("evil.pdf", "content", kb_dir=live_kb)

    def test_traversal_name_stays_inside_kb(self, live_kb):
        info = ingest_document("../escape.md", "harmless content here.", kb_dir=live_kb)
        assert info["filename"] == "escape.md"
        assert (live_kb / "escape.md").exists()
        assert not (live_kb.parent / "escape.md").exists()

    def test_rejects_empty_and_oversize(self, live_kb):
        with pytest.raises(ValueError, match="empty"):
            ingest_document("empty.md", "   ", kb_dir=live_kb)
        with pytest.raises(ValueError, match="exceeds"):
            ingest_document("big.md", "x" * (vs.MAX_DOC_CHARS + 1), kb_dir=live_kb)

    def test_list_documents_counts(self, live_kb):
        ingest_document("extra.md", "# Extra\n\nSome filler words.", kb_dir=live_kb)
        docs = list_documents(live_kb)
        assert {d["filename"] for d in docs} == {"seed.md", "extra.md"}
        assert all(d["chunks"] >= 1 for d in docs)


class TestKbApi:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vs, "KB_DIR", tmp_path)
        reset_vector_store()
        from fastapi.testclient import TestClient

        from api import app

        yield TestClient(app)
        reset_vector_store()

    def test_upload_then_list(self, client):
        r = client.post(
            "/api/v1/kb/documents",
            json={
                "filename": "api_probe.md",
                "content": "# API Probe\n\nQuokka handling procedures.\n",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["filename"] == "api_probe.md"
        assert body["created"] is True

        listed = client.get("/api/v1/kb/documents").json()["documents"]
        assert "api_probe.md" in {d["filename"] for d in listed}

        hits = get_vector_store().search("quokka handling")
        assert hits and hits[0][0].source == "api_probe.md"

    def test_upload_rejects_bad_type(self, client):
        r = client.post(
            "/api/v1/kb/documents",
            json={"filename": "nope.exe", "content": "junk"},
        )
        assert r.status_code == 422
