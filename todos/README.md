# TrustLoop — Next Steps & Action Checklist

Welcome to the TrustLoop implementation guide. All requested features have been developed, integrated, and verified:

1. **Dual-Engine Database (PostgreSQL + SQLite)**:
   - Full PostgreSQL support via `psycopg2-binary`.
   - Seamless, zero-crash fallback to SQLite if PostgreSQL is offline or credentials are not yet entered.
   - Supports runs, answers, immutable audit events, API key management, and video transcriptions.

2. **Video & Audio Transcription Pipeline**:
   - Accepts `.mp4`, `.mov`, `.webm`, `.mkv`, `.avi`, `.m4a`, `.mp3`, `.wav`.
   - Extracts 16kHz mono audio using self-contained `imageio-ffmpeg` binary (zero system dependencies).
   - Transcribes spoken dialogue with **Groq Whisper** (`whisper-large-v3`, free tier, open source), **OpenAI Whisper** (`whisper-1`), **Deepgram** (Nova-2), and an offline deterministic fallback.
   - Automatically detects and parses security compliance questions from dialogue.
   - Passes extracted questions through TrustLoop's LangGraph verification and compliance guardrail pipeline.

3. **Public Developer API & API Key Management**:
   - Generate, list, and revoke dynamic API keys directly from the UI dashboard or via REST endpoints.
   - Authenticated access via `X-API-Key` or `Authorization: Bearer <key>`.
   - Endpoints for questionnaire parsing, pipeline execution, batch runs, quality assessment, video transcription, and knowledge base ingestion.
   - Built-in Swagger UI at `/docs` and interactive code samples in Python, cURL, and JavaScript.

4. **Dark Mode & Light Mode Theme Toggle**:
   - Instant 1-click toggle between 🌙 Dark Mode (enterprise dark) and ☀️ Light Mode (clean enterprise slate/white).
   - Available in both the landing page and workspace sidebars.
   - Complete styling of all cards, buttons, badges, tables, inputs, and layout blocks.

---

## 📋 What You Need To Do

To run TrustLoop in full live mode with your external services, follow these simple guides:

- **[API Keys Checklist](API_KEYS_CHECKLIST.md)**: Where to get free API keys for Groq, OpenAI, or Deepgram and paste them into `.env`.
- **[PostgreSQL Setup Guide](POSTGRES_SETUP.md)**: How to set your password and connect to your local PostgreSQL server.
- **[Running & Deployment Guide](DEPLOYMENT_AND_RUN.md)**: Commands to start the UI and REST API server.
