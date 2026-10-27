# PostgreSQL Setup & Database Guide

TrustLoop supports a **Dual-Engine Architecture**:
- When PostgreSQL credentials are provided in `.env`, TrustLoop connects to PostgreSQL.
- If PostgreSQL is offline, unreachable, or credentials are not yet entered, TrustLoop automatically and safely falls back to local SQLite (`data/trustloop.db`).

---

## 1. Quick Setup on Your Machine

Your Windows system already has PostgreSQL 18 installed and running as a service (`postgresql-x64-18`) on `localhost:5432`.

### Step 1: Create the `trustloop` Database
Open PowerShell or Command Prompt and run:
```bash
psql -U postgres -h localhost -c "CREATE DATABASE trustloop;"
```
*(Enter your PostgreSQL password when prompted)*

### Step 2: Configure `.env`
Open `.env` in the project root (`d:\TrustLoop\.env`) and add:
```bash
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/trustloop
```
*(Replace `YOUR_PASSWORD` with the password you set during PostgreSQL installation).*

Alternatively, you can provide individual fields:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=trustloop
POSTGRES_USER=postgres
POSTGRES_PASSWORD=YOUR_PASSWORD
```

---

## 2. Verifying the Connection

You can verify the connection at any time by running:
```powershell
.\.venv\Scripts\python -c "from storage import db; print('Active database engine:', db.get_database_engine())"
```
- If connected: prints `Active database engine: postgresql`
- If falling back: prints `Active database engine: sqlite`

---

## 3. Database Schema Overview

When TrustLoop connects, it automatically creates the following tables:
1. `runs`: Records each questionnaire pipeline execution.
2. `answers`: Stores question drafts, evidence citations, confidence scores, risk flags, and reviewer edits.
3. `audit_events`: Immutable audit trail tracking every system and human reviewer action.
4. `api_keys`: Dynamic developer API keys, hashed secrets, previews, and rate limits.
5. `transcriptions`: Stores video/audio file transcripts, question detections, and run linkages.

All tables are created automatically on application start — no manual migrations required!
