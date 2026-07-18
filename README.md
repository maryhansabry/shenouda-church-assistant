# Shenouda | Church AI Assistant

**An AI assistant (RAG) for Anba Shenouda Church** — answers visitor questions about the church's history and priests based strictly on documented sources, via text or voice, with real-time voice call support.

(<img width="1920" height="930" alt="image" src="https://github.com/user-attachments/assets/074d476c-e89f-4c34-a9f5-bfa38499b3c0" />
)
(<img width="1920" height="917" alt="image" src="https://github.com/user-attachments/assets/c89d2f59-3b5f-4ea1-8efb-5daa19b0361c" />
https://shenouda-church-assistant.vercel.app/

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Tech Stack](#tech-stack)
- [License](#license)

---

## Overview

The project is split into two independent parts:

| Part | Responsibility | Stack |
|---|---|---|
| **Frontend** | Arabic chat UI: text, voice messages, real-time call | React + Vite + Tailwind |
| **Backend** | Receives the question, retrieves the closest matching context, generates a text + audio reply | FastAPI + FAISS + LLM APIs |

The knowledge base (church history) is pre-built as embeddings (`chunks.pkl`, `embeddings.npy`, `faiss.index`) — it isn't regenerated on every startup.

---

## Features

- **Source-grounded answers only** — the model is instructed never to invent facts, and preserves clerical titles (القمص, الأنبا, القس...) and names exactly as they appear in the source material
- **LLM fallback chain** — Cerebras is the primary provider; on failure it automatically falls back through two Groq models in sequence, with no noticeable interruption for the user
- **Context-aware images** — when a specific person or event is mentioned, relevant photos are retrieved from Cloudinary
- **Text ↔ speech**
  - Text → speech: Gemini TTS (with ElevenLabs support)
  - Speech → text: faster-whisper locally, or Groq Whisper as a faster cloud option
- **Real-time voice call** over WebSocket — speech recognition happens in the browser (Web Speech API), and the audio reply is streamed back in small chunks with barge-in (interruption) support
- **Easter egg** — special greeting phrases (e.g. welcoming His Holiness the Pope) trigger a recorded hymn instead of the usual reply

---

## Architecture

```
┌─────────────┐      HTTP / WebSocket      ┌──────────────────┐
│   Frontend   │ ─────────────────────────▶ │     Backend      │
│  React+Vite  │ ◀───────────────────────── │     FastAPI      │
└─────────────┘        JSON / audio          └────────┬─────────┘
                                                        │
                                       ┌────────────────┼────────────────┐
                                       ▼                ▼                ▼
                                 FAISS Retrieval   LLM (Cerebras/Groq)  TTS/STT
                                 (chunks.pkl)      + fallback chain    (Gemini/
                                                                    ElevenLabs/Whisper)
```

---

## Project Structure

```
shenouda-church-assistant/
├── backend/                 # FastAPI service (deploy to Railway)
│   ├── main.py                # Entry point + resource loading on startup
│   ├── routes.py              # /chat  /voice  /tts  /ws/call  /health
│   ├── rag.py                  # Retrieval + LLM calls + fallback + images
│   ├── models.py                # Pydantic request/response schemas
│   ├── config.py                 # All environment variables
│   ├── requirements.txt
│   ├── chunks.pkl / embeddings.npy / faiss.index   # pre-built knowledge base
│   └── .env.example
│
├── frontend/                # React app (deploy to Vercel)
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vercel.json
│   └── .env.example
│
├── README.md
└── LICENSE
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- API keys for: Cerebras and/or Groq (chat), Gemini and/or ElevenLabs (voice) — depending on which features you want enabled

### Backend

```bash
cd backend
cp .env.example .env      # then fill in your keys inside .env
pip install -r requirements.txt
uvicorn main:app --reload
```
Runs on `http://localhost:8000`

> ⚠️ The backend loads `torch` and `faster-whisper` for local speech recognition, which takes noticeable time and memory on first startup. This is also why some free hosting tiers aren't sufficient for this project — see [Deployment](#deployment).

### Frontend

```bash
cd frontend
cp .env.example .env      # VITE_API_URL=http://localhost:8000
npm install
npm run dev
```
Runs on `http://localhost:5173`

---

## Environment Variables

**`backend/.env`**

```env
# LLM (chat) — Cerebras primary, automatic fallback to Groq
CEREBRAS_API_KEY=
GROQ_API_KEY=
GROQ_SECONDARY_MODEL=llama-3.3-70b-versatile
GROQ_TERTIARY_MODEL=llama-3.1-8b-instant

# Speech-to-Text
HF_TOKEN=
GROQ_STT_MODEL=whisper-large-v3-turbo

# Text-to-Speech
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
GEMINI_API_KEY=
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_TTS_VOICE=Kore
```

**`frontend/.env`**

```env
VITE_API_URL=http://localhost:8000
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Text question → text reply + optional images + optional audio URL |
| `POST` | `/voice` | Upload audio file → transcript + text and voice reply |
| `POST` | `/tts` | Convert text to speech (Gemini TTS) |
| `WS` | `/ws/call` | Real-time streamed voice call |

---

## Deployment

### Frontend → Vercel

1. Import the project, set **Root Directory** to `frontend`
2. Add the environment variable `VITE_API_URL` pointing to your backend URL
3. Deploy

### Backend → Railway

1. Create a new project on [railway.app](https://railway.app) and link this GitHub repository
2. Set the **Root Directory** to `backend`
3. Railway auto-detects Python; set the start command to:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. Add all the environment variables listed above under the service's **Variables** tab
5. Deploy

> Because of the heavier audio libraries (`torch`, `faster-whisper`), keep an eye on memory usage — Railway's free tier has usage-based limits, so it's worth checking current pricing before deploying if cost is a concern. As alternatives with no upfront cost:
> - Run the backend locally only (`localhost`) for testing/demo purposes
> - Temporarily remove local speech recognition from `requirements.txt` to shrink the footprint while keeping text chat fully functional

---

## Tech Stack

**Frontend:** React 18 · Vite 6 · TypeScript · Tailwind CSS · Axios · React Icons

**Backend:** FastAPI · FAISS · sentence-transformers · faster-whisper · Cerebras · Groq · ElevenLabs · Gemini · Cloudinary

**Real-time:** WebSockets · Web Speech API (client-side)

---

## License

Licensed under the [MIT License](./LICENSE).
