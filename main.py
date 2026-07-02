from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from routes import router
import rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all ML resources once at startup."""
    rag.load_resources()
    yield
    # Cleanup on shutdown (nothing needed for read-only resources)


app = FastAPI(
    title="شنودة — Church AI Assistant",
    description="RAG-powered assistant for Anba Shenouda Church",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=CORS_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
