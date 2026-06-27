import os
import pickle
import numpy as np
import faiss
import requests

from config import (
    CHUNKS_PATH, HF_TOKEN, HF_EMBED_URL,
    GROQ_API_KEY, GROQ_CHAT_MODEL, TOP_K, SYSTEM_PROMPT,
)

_chunks: list[str] = []
_index: faiss.Index | None = None


def _hf_embed(texts: list[str]) -> np.ndarray:
    resp = requests.post(
        HF_EMBED_URL,
        headers={"Authorization": f"Bearer {HF_TOKEN}"},
        json={"inputs": texts, "options": {"wait_for_model": True}},
        timeout=60,
    )
    resp.raise_for_status()
    return np.array(resp.json(), dtype=np.float32)


def load_resources() -> None:
    global _chunks, _index
    print("Loading chunks...")
    with open(CHUNKS_PATH, "rb") as f:
        _chunks = pickle.load(f)
    _chunks = [c["text"] if isinstance(c, dict) else c for c in _chunks]
    print(f"Embedding {len(_chunks)} chunks with HuggingFace...")
    vectors = _hf_embed(_chunks)
    dim = vectors.shape[1]
    faiss.normalize_L2(vectors)
    _index = faiss.IndexFlatIP(dim)
    _index.add(vectors)
    print(f"✅ Ready — {len(_chunks)} chunks, dim={dim}")


def _retrieve_context(question: str) -> str:
    vec = _hf_embed([question])
    faiss.normalize_L2(vec)
    _, indices = _index.search(vec, TOP_K)
    retrieved = [_chunks[i] for i in indices[0] if 0 <= i < len(_chunks)]
    return "\n\n".join(retrieved)
  

def answer_question(question: str) -> str:
    context = _retrieve_context(question)
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_CHAT_MODEL,
            "temperature": 0.3,
            "max_tokens": 800,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"السياق:\n{context}\n\nالسؤال: {question}\n\nأجب بناءً على السياق فقط."},
            ],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()