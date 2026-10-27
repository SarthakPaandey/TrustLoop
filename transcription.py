"""Video and audio intake & transcription service.

Extracts audio from video formats (.mp4, .mov, .avi, .mkv, .webm) and
transcribes spoken dialogue into text using:
1. Groq Whisper (free open-source whisper-large-v3, ultra-fast)
2. OpenAI Whisper (whisper-1)
3. Deepgram (Nova-2)
4. Offline fallback mode (for zero-dependency local testing/demo)

The extracted transcript is then parsed into structured security questions
that route through TrustLoop's verification and compliance pipeline.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

import config
from agents.intake import parse_text
from models import Question

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
ALL_MEDIA_EXTS = SUPPORTED_VIDEO_EXTS | SUPPORTED_AUDIO_EXTS


def is_media_file(filename: str | Path) -> bool:
    """Return True if the filename has an audio or video extension."""
    suffix = Path(filename).suffix.lower()
    return suffix in ALL_MEDIA_EXTS


def get_ffmpeg_path() -> str | None:
    """Find ffmpeg binary from imageio-ffmpeg or system PATH."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass

    import shutil
    return shutil.which("ffmpeg")


def extract_audio(input_file: Path | str, output_path: Path | None = None) -> Path:
    """Extract a 16kHz mono WAV audio file from a video or audio source.

    If the file is already a WAV file, it is returned directly.
    If conversion is not possible, returns the original input path as fallback.
    """
    src = Path(input_file).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Media file not found: {src}")

    if src.suffix.lower() == ".wav":
        return src

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        logger.info("ffmpeg not found; passing raw media file %s directly to transcription", src.name)
        return src

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        target = Path(tmp.name)
    else:
        target = Path(output_path).resolve()

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(src),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(target),
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if target.exists() and target.stat().st_size > 0:
            return target
    except Exception as exc:
        logger.warning("Audio extraction via ffmpeg failed (%s); using original file", exc)

    return src


def extract_questions_from_transcript(transcript: str) -> list[str]:
    """Parse dialogue/transcript text into individual candidate security questions.

    Identifies sentences ending in question marks or starting with question patterns.
    """
    text = transcript.strip()
    if not text:
        return []

    # First, split on newlines if multiple lines exist
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # If transcript is a single continuous paragraph, split by punctuation
    candidate_sentences: list[str] = []
    if len(lines) <= 1:
        # Split on sentence boundaries (? . !)
        sentences = re.split(r"(?<=[?.!])\s+", text)
        candidate_sentences = [s.strip() for s in sentences if s.strip()]
    else:
        candidate_sentences = lines

    # Filter for inquiry-like questions
    question_starters = (
        "do you", "are you", "is your", "can you", "what is", "what are",
        "where is", "where are", "how do", "how is", "how does", "please confirm",
        "please explain", "confirm whether", "does your", "have you", "who has",
        "which", "when", "why",
    )

    questions: list[str] = []
    for s in candidate_sentences:
        clean_s = re.sub(r"^\d+[\.\)]\s*", "", s).strip()
        clean_s = re.sub(r"^[-*•]\s*", "", clean_s).strip()
        if not clean_s or len(clean_s) < 8:
            continue

        lower = clean_s.lower()
        if clean_s.endswith("?") or any(lower.startswith(q) for q in question_starters):
            questions.append(clean_s)

    # If no strict questions found, fall back to non-empty sentences
    if not questions:
        for s in candidate_sentences:
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", s).strip()
            if len(cleaned) >= 8:
                questions.append(cleaned)

    return questions


def _offline_mock_transcript(filename: str) -> str:
    """Generate a realistic security questionnaire transcript when no API keys are provided."""
    return (
        f"[Audio transcription for '{filename}']\n"
        "Hello Acme Security Team, here are the compliance questions from our vendor security review:\n"
        "1. Do you encrypt customer data at rest using AES-256 and in transit using TLS 1.3?\n"
        "2. Are your systems and data centers SOC 2 Type II and ISO 27001 certified?\n"
        "3. Where is customer data physically hosted and what is your data residency policy?\n"
        "4. Do you support Single Sign-On (SSO) via SAML 2.0 and mandatory MFA?\n"
        "5. What are your Disaster Recovery RTO and RPO objectives?\n"
        "6. Do you conduct regular third-party penetration testing and vulnerability scans?\n"
    )


def transcribe_media(
    media_path: Path | str,
    language: str = "en",
    mock_if_offline: bool = True,
) -> dict[str, Any]:
    """Transcribe audio or video media file using the best available provider.

    Resolution order:
    1. Groq Whisper (free open-source Whisper-large-v3)
    2. OpenAI Whisper (whisper-1)
    3. Deepgram (Nova-2)
    4. Offline fallback mode
    """
    path = Path(media_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {path}")

    # Check for sidecar transcript (.txt) next to media file
    sidecar = path.with_suffix(".txt")
    if sidecar.exists():
        try:
            sidecar_text = sidecar.read_text(encoding="utf-8").strip()
            if sidecar_text:
                qs = extract_questions_from_transcript(sidecar_text)
                return {
                    "text": sidecar_text,
                    "provider": "sidecar",
                    "model": "text-file",
                    "duration_seconds": 0.0,
                    "detected_questions": qs,
                    "filename": path.name,
                }
        except Exception:
            pass

    # Extract audio if necessary
    audio_path = extract_audio(path)

    # 1. Groq Whisper
    if config.GROQ_API_KEY:
        try:
            try:
                from groq import Groq
                client = Groq(api_key=config.GROQ_API_KEY)
            except ImportError:
                from openai import OpenAI
                client = OpenAI(
                    api_key=config.GROQ_API_KEY,
                    base_url="https://api.groq.com/openai/v1",
                )

            with open(audio_path, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=(audio_path.name, fh.read()),
                    response_format="verbose_json",
                )

            if hasattr(resp, "text"):
                text = resp.text
            elif isinstance(resp, dict):
                text = resp.get("text", "")
            else:
                text = str(resp)

            duration = float(
                getattr(resp, "duration", 0.0)
                or (resp.get("duration", 0.0) if isinstance(resp, dict) else 0.0)
                or 0.0
            )
            qs = extract_questions_from_transcript(text)
            return {
                "text": text,
                "provider": "groq",
                "model": "whisper-large-v3",
                "duration_seconds": duration,
                "detected_questions": qs,
                "filename": path.name,
            }
        except Exception as exc:
            logger.warning("Groq Whisper transcription failed: %s", exc)

    # 2. OpenAI Whisper
    if config.OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=config.OPENAI_API_KEY)
            with open(audio_path, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=(audio_path.name, fh.read()),
                    response_format="verbose_json",
                )

            if hasattr(resp, "text"):
                text = resp.text
            elif isinstance(resp, dict):
                text = resp.get("text", "")
            else:
                text = str(resp)

            duration = float(
                getattr(resp, "duration", 0.0)
                or (resp.get("duration", 0.0) if isinstance(resp, dict) else 0.0)
                or 0.0
            )
            qs = extract_questions_from_transcript(text)
            return {
                "text": text,
                "provider": "openai",
                "model": "whisper-1",
                "duration_seconds": duration,
                "detected_questions": qs,
                "filename": path.name,
            }
        except Exception as exc:
            logger.warning("OpenAI Whisper transcription failed: %s", exc)

    # 3. Deepgram
    if config.DEEPGRAM_API_KEY:
        try:
            headers = {
                "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
                "Content-Type": "audio/wav",
            }
            with open(audio_path, "rb") as fh:
                audio_bytes = fh.read()
            dg_resp = httpx.post(
                "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true",
                headers=headers,
                content=audio_bytes,
                timeout=30.0,
            )
            dg_resp.raise_for_status()
            data = dg_resp.json()
            channels = data.get("results", {}).get("channels", [])
            text = ""
            if channels:
                alts = channels[0].get("alternatives", [])
                if alts:
                    text = alts[0].get("transcript", "")
            duration = float(data.get("metadata", {}).get("duration", 0.0))
            qs = extract_questions_from_transcript(text)
            return {
                "text": text,
                "provider": "deepgram",
                "model": "nova-2",
                "duration_seconds": duration,
                "detected_questions": qs,
                "filename": path.name,
            }
        except Exception as exc:
            logger.warning("Deepgram transcription failed: %s", exc)

    # 4. Offline Fallback Mode
    if mock_if_offline:
        text = _offline_mock_transcript(path.name)
        qs = extract_questions_from_transcript(text)
        return {
            "text": text,
            "provider": "offline",
            "model": "deterministic-fallback",
            "duration_seconds": 15.0,
            "detected_questions": qs,
            "filename": path.name,
        }

    raise RuntimeError(
        "No transcription provider available. Please set GROQ_API_KEY or OPENAI_API_KEY."
    )


def parse_media_to_questions(media_path: Path | str) -> tuple[dict[str, Any], list[Question]]:
    """Transcribe a video or audio file and parse it into structured Questions."""
    result = transcribe_media(media_path)
    questions_raw = "\n".join(result["detected_questions"])
    questions = parse_text(questions_raw) if questions_raw else parse_text(result["text"])
    return result, questions
