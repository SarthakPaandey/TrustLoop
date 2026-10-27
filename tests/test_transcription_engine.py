"""Tests for video & audio transcription, ffmpeg extraction, and questionnaire parsing."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
from agents.intake import parse_questionnaire
from transcription import (
    ALL_MEDIA_EXTS,
    extract_audio,
    extract_questions_from_transcript,
    get_ffmpeg_path,
    is_media_file,
    parse_media_to_questions,
    transcribe_media,
)


def test_is_media_file():
    """Verify supported extensions detection."""
    assert is_media_file("interview.mp4") is True
    assert is_media_file("briefing.mov") is True
    assert is_media_file("audio.wav") is True
    assert is_media_file("podcast.mp3") is True
    assert is_media_file("document.txt") is False
    assert is_media_file("sheet.xlsx") is False
    assert is_media_file("policy.md") is False


def test_ffmpeg_availability():
    """Verify that bundled imageio-ffmpeg binary is discovered."""
    ffmpeg = get_ffmpeg_path()
    assert ffmpeg is not None
    assert Path(ffmpeg).exists()


def test_extract_questions_from_transcript():
    """Test extracting clean security questions from conversational text."""
    dialogue = (
        "Good morning everyone. Today we are conducting our vendor security evaluation.\n"
        "First question: Do you encrypt data at rest using AES-256?\n"
        "Second: Are all your data centers SOC 2 Type II certified?\n"
        "Also, where is customer data physically hosted?\n"
        "Thank you, that concludes the call."
    )
    questions = extract_questions_from_transcript(dialogue)
    assert len(questions) >= 3
    assert any("encrypt data at rest" in q.lower() for q in questions)
    assert any("soc 2" in q.lower() for q in questions)
    assert any("where is customer data" in q.lower() for q in questions)
    # Greetings and closing statements should be excluded
    assert not any("good morning" in q.lower() for q in questions)
    assert not any("concludes the call" in q.lower() for q in questions)


def test_transcribe_media_offline_fallback():
    """Test deterministic offline mode when no API keys are provided."""
    with patch.object(config, "GROQ_API_KEY", ""), patch.object(config, "OPENAI_API_KEY", ""):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"\x00\x00\x00 ftypisom")  # Minimal dummy header
            tmp_path = Path(tmp.name)

        try:
            res = transcribe_media(tmp_path, mock_if_offline=True)
            assert res is not None
            assert res["provider"] == "offline"
            assert len(res["detected_questions"]) >= 4
            assert any("encrypt" in q.lower() for q in res["detected_questions"])
            assert any("soc 2" in q.lower() for q in res["detected_questions"])
        finally:
            tmp_path.unlink()


def test_transcribe_media_with_groq_mock():
    """Test transcription through Groq Whisper API client."""
    mock_response = MagicMock()
    mock_response.text = "Do you have SOC 2 Type II attestation? Where is data stored?"
    mock_response.duration = 18.2

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_response

    with patch.object(config, "GROQ_API_KEY", "gsk_dummy_test_key"):
        with patch("groq.Groq", return_value=mock_client), patch("openai.OpenAI", return_value=mock_client):
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00")
                tmp_path = Path(tmp.name)

            try:
                res = transcribe_media(tmp_path)
                assert res["provider"] == "groq"
                assert res["model"] == "whisper-large-v3"
                assert res["duration_seconds"] == 18.2
                assert len(res["detected_questions"]) >= 2
                assert "SOC 2" in res["text"]
            finally:
                tmp_path.unlink()


def test_parse_media_to_questions_and_intake():
    """Test end-to-end media intake that emits Question models."""
    with patch.object(config, "GROQ_API_KEY", ""), patch.object(config, "OPENAI_API_KEY", ""):
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(b"\x1a\x45\xdf\xa3")
            tmp_path = Path(tmp.name)

        try:
            meta, questions = parse_media_to_questions(tmp_path)
            assert len(questions) > 0
            assert all(q.id.startswith("Q-") for q in questions)
            assert all(q.category in ("technical", "certification", "data-privacy", "legal", "general") for q in questions)

            # Test through agents.parse_questionnaire directly
            intake_qs = parse_questionnaire(tmp_path)
            assert len(intake_qs) == len(questions)
        finally:
            tmp_path.unlink()
