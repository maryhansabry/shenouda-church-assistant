import pickle
import numpy as np
import faiss
import requests

from sentence_transformers import SentenceTransformer

from config import (
    CHUNKS_PATH,
    GROQ_API_KEY,
    GROQ_CHAT_MODEL,
    TOP_K,
    SYSTEM_PROMPT,
    EMBED_MODEL,
    MIN_SIMILARITY,
)

_chunks: list[str] = []
_index: faiss.Index | None = None
_embedder = None

def load_resources():
    global _chunks, _index, _embedder

    print("Loading chunks...")

    with open(CHUNKS_PATH, "rb") as f:
        _chunks = pickle.load(f)

    _chunks = [
        c["text"] if isinstance(c, dict) else c
        for c in _chunks
    ]

    print("Loading embedding model...")

    _embedder = SentenceTransformer(
        EMBED_MODEL
    )

    print("Loading embeddings...")

    vectors = np.load("embeddings.npy").astype(np.float32)

    faiss.normalize_L2(vectors)

    _index = faiss.IndexFlatIP(vectors.shape[1])

    _index.add(vectors)

    print("✅ Backend Ready")


def _embed_question(question):
    vector = _embedder.encode(
        [question],
        normalize_embeddings=True
    )

    return np.asarray(
        vector,
        dtype=np.float32
    )



def _retrieve_context(question):

    vec = _embed_question(question)

    scores, indices = _index.search(
        vec,
        TOP_K
    )

    retrieved = []

    for score, idx in zip(scores[0], indices[0]):

        if score < MIN_SIMILARITY:
            continue

        retrieved.append(_chunks[idx])

    return "\n\n".join(retrieved)


def answer_question(question):

    context = _retrieve_context(question)

    if not context.strip():
        return (
            "عذرًا، لا أملك معلومة مؤكدة عن ذلك. "
            "يرجى الرجوع لقدس أبونا ويصا."
        )

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_CHAT_MODEL,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content":
                    f"""
السياق:

{context}

السؤال:

{question}

أجب اعتمادًا على السياق فقط.
""",
                },
            ],
        },
    )

    resp.raise_for_status()

    return resp.json()["choices"][0]["message"]["content"]
