# شنودة — Church AI Assistant

A production-ready RAG-powered AI assistant for Anba Shenouda Church.

---

## Project Structure

```
project/
├── frontend/          # React + Vite + Tailwind (deploy to Vercel)
└── backend/           # FastAPI + FAISS + OpenAI (deploy to Render)
```

---

## Quick Start (Local Development)

### Backend

```bash
cd backend

# Copy env file and add your OpenAI key
cp .env.example .env
# Edit .env: OPENAI_API_KEY=sk-...

# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn main:app --reload
# Runs at http://localhost:8000
```

### Frontend

```bash
cd frontend

# Copy env file
cp .env.example .env
# Edit .env if backend is not on localhost:8000

# Install dependencies
npm install

# Start dev server
npm run dev
# Runs at http://localhost:5173
```

---

## Adding the Assistant Avatar

Place your image at:

```
frontend/public/avatar/avatar.png
```

The assistant will automatically display it. If the file doesn't exist, a default church icon is shown.

---

## Deployment

### Backend → Render

1. Push `backend/` to a GitHub repo
2. Create a new **Web Service** on [render.com](https://render.com)
3. Connect the repo
4. Set the environment variable: `OPENAI_API_KEY=sk-...`
5. Render auto-detects `render.yaml` for build/start commands

### Frontend → Vercel

1. Push `frontend/` to a GitHub repo
2. Import the project on [vercel.com](https://vercel.com)
3. Add environment variable: `VITE_API_URL=https://your-render-url.onrender.com`
4. Deploy

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/chat` | Text RAG chat |
| POST | `/voice` | Voice input → spoken answer |

---

## Environment Variables

**Backend** (`.env`):
```
OPENAI_API_KEY=sk-...
```

**Frontend** (`.env`):
```
VITE_API_URL=http://localhost:8000
```

---

## Tech Stack

- **Frontend**: React, Vite, TypeScript, Tailwind CSS, Axios, React Icons
- **Backend**: FastAPI, sentence-transformers, FAISS, OpenAI API
- **Embeddings**: Pre-built (`chunks.pkl`, `embeddings.npy`, `faiss.index`) — never regenerated
