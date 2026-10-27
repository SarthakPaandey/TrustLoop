# API Keys Setup & Provider Checklist

TrustLoop is designed to operate seamlessly in both **offline demo mode** (zero keys required) and **live cloud mode** (using free tier / open-source API keys).

Below is the list of recommended API keys to paste into your `.env` file.

---

## 1. Groq API Key (Recommended — Free & Open Source)
- **What it provides**:
  - Ultra-fast Whisper Large v3 audio/video speech-to-text transcription (`whisper-large-v3`).
  - Llama 3.3 70B inference for answer generation (`llama-3.3-70b-versatile`).
- **Cost**: **100% Free tier** available.
- **Where to get**:
  1. Go to [https://console.groq.com](https://console.groq.com)
  2. Sign in with Google or GitHub.
  3. Navigate to **API Keys** -> click **Create API Key**.
  4. Copy the key (starts with `gsk_...`).
- **In your `.env`**:
  ```bash
  GROQ_API_KEY=gsk_your_groq_api_key_here
  GROQ_MODEL=llama-3.3-70b-versatile
  ```

---

## 2. OpenAI API Key (Alternative)
- **What it provides**:
  - Whisper-1 speech-to-text for video and audio uploads.
  - GPT-4o-mini LLM inference for draft question answers.
- **Cost**: Pay-as-you-go / free trial credits on new accounts.
- **Where to get**:
  1. Go to [https://platform.openai.com](https://platform.openai.com)
  2. Navigate to **API Keys** -> click **Create new secret key**.
- **In your `.env`**:
  ```bash
  OPENAI_API_KEY=sk-proj-...
  OPENAI_MODEL=gpt-4o-mini
  ```

---

## 3. Deepgram API Key (Optional Alternative)
- **What it provides**:
  - Nova-2 speech-to-text for recorded videos and meeting calls.
- **Cost**: **$200 in free credits** on sign-up with no credit card required.
- **Where to get**:
  1. Go to [https://console.deepgram.com](https://console.deepgram.com)
  2. Sign up and copy your API key.
- **In your `.env`**:
  ```bash
  DEEPGRAM_API_KEY=your_deepgram_api_key_here
  ```

---

## 4. Master Developer API Key (Optional)
- **What it provides**:
  - A master token that can authenticate all requests to the REST API (`/api/v1/*`).
  - Note: You can also generate individual dynamic client API keys directly from the **Developer API** tab in the Streamlit UI!
- **In your `.env`**:
  ```bash
  TRUSTLOOP_API_KEY=tl_live_master_key_12345
  ```

---

## Summary of Priority
If you only want to set up **ONE** free service for both LLM reasoning and video transcription:
👉 **Set `GROQ_API_KEY`!**
Groq provides both Whisper Large v3 (for video/audio transcription) and Llama 3.3 (for question answering) for free!
