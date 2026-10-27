# Running & Deployment Guide

This guide describes how to run TrustLoop locally and deploy it to production.

---

## 1. Running Locally

### Start the Streamlit UI (Dark/Light Mode + Video Intake + Workspace)
In PowerShell:
```powershell
.\.venv\Scripts\streamlit run app.py
```
- Opens in your browser at `http://localhost:8501`.
- Use the sidebar toggle to switch between **🌙 Dark Mode** and **☀️ Light Mode**.
- Upload `.xlsx`, `.txt`, or video files (`.mp4`, `.mov`, `.webm`, etc.) in the **Questionnaires** tab.
- Manage and create developer keys in the **Developer API** tab.

### Start the FastAPI Server (REST API & Integrations)
In a separate terminal:
```powershell
.\.venv\Scripts\uvicorn api:app --reload --port 8000
```
- Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Interactive ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Health check: `http://localhost:8000/api/v1/health`

---

## 2. Testing the Developer API

### Generate an API Key via cURL:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{"name": "CLI Client", "rate_limit": 100}'
```
Response:
```json
{
  "key_id": "key_7a8b9c...",
  "name": "CLI Client",
  "api_key": "tl_live_...",
  "key_preview": "tl_live_7a8...c3d1",
  "created_at": "2026-10-27T21:30:00Z",
  "rate_limit": 100,
  "is_active": true
}
```

### Run Questionnaire Verification:
```bash
curl -X POST "http://localhost:8000/api/v1/run" \
  -H "X-API-Key: tl_live_..." \
  -H "Content-Type: application/json" \
  -d '{"text": "Do you encrypt data at rest?\nAre you SOC 2 Type II certified?"}'
```

### Run Video Questionnaire Verification:
```bash
curl -X POST "http://localhost:8000/api/v1/video/run" \
  -H "X-API-Key: tl_live_..." \
  -F "file=@meeting_recording.mp4"
```

---

## 3. Running Automated Tests

Run the full end-to-end test suite:
```powershell
.\.venv\Scripts\pytest -v
```

---

## 4. Production Deployment

### Option A: Docker
A multi-stage `Dockerfile` is provided in the repository root.
```bash
docker build -t trustloop:latest .
docker run -p 8501:8501 -e DATABASE_URL="postgresql://user:pass@host:5432/trustloop" trustloop:latest
```

### Option B: Cloud PostgreSQL (Supabase / Neon / AWS RDS)
1. Create a free PostgreSQL instance on [Supabase](https://supabase.com) or [Neon](https://neon.tech).
2. Copy the connection string to your `DATABASE_URL` environment variable.
3. TrustLoop will automatically establish the schema and persist all data to the cloud database!
