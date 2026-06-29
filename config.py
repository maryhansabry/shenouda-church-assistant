import os
from dotenv import load_dotenv
load_dotenv()
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

TOP_K = 7

MIN_SIMILARITY = 0.35
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
HF_TOKEN: str = os.getenv("HF_TOKEN", "")

GROQ_CHAT_MODEL: str = "llama-3.1-8b-instant"
HF_EMBED_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
HF_EMBED_URL: str = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{HF_EMBED_MODEL}"

TTS_VOICE: str = "ar-EG-ShakirNeural"
WHISPER_MODEL: str = "tiny"
TOP_K: int = 5
CHUNKS_PATH: str = "chunks.pkl"
CORS_ORIGINS: list = ["*"]

SYSTEM_PROMPT: str = """أنت "شنودة"، مساعد ذكي خاص بكنيسة الأنبا شنودة.
1. أجب فقط بناءً على المعلومات الموجودة في السياق المقدم لك.
2. إذا لم تجد المعلومة: "عذرًا، لا أملك معلومة مؤكدة عن ذلك. يرجى الرجوع لقدس أبونا ويصا."
3. لا تخترع معلومات.
4. لا تذكر: embeddings, FAISS, retrieval, chunks.
5. تحدث بشكل طبيعي وودي.
6. لا تدّعي أنك قسيس أو كاهن.
7. إذا سألك عن هويتك: "أنا شنودة، مساعد ذكي خاص بالكنيسة."
"""
