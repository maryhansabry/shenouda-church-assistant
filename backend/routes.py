import io
import json
import base64
import asyncio
import tempfile
import os
import traceback

from fastapi import APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from faster_whisper import WhisperModel

from models import ChatRequest, ChatResponse, HealthResponse
from config import WHISPER_MODEL, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
import rag

router = APIRouter()

# =========================
# Whisper
# =========================

_whisper = None

def get_whisper():
    global _whisper

    if _whisper is None:
        print(f"Loading Whisper model ({WHISPER_MODEL})...")

        _whisper = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8"
        )

        print("✅ Whisper loaded successfully")

    return _whisper


# =========================
# TTS (ElevenLabs)
# # =========================
# from elevenlabs.client import ElevenLabs

# _elevenlabs_client = None

# def get_elevenlabs():
#     global _elevenlabs_client

#     if _elevenlabs_client is None:
#         print("Initializing ElevenLabs client...")
#         _elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
#         print("✅ ElevenLabs client ready")

#     return _elevenlabs_client


# def _text_to_speech_sync(text: str) -> bytes:
#     try:
#         print(f"TTS Request: {text[:100]}")

#         client = get_elevenlabs()

#         audio_stream = client.text_to_speech.convert(
#             voice_id=ELEVENLABS_VOICE_ID,
#             text=text,
#             model_id="eleven_multilingual_v2",
#             output_format="mp3_44100_128",
#         )

#         audio_data = b"".join(audio_stream)

#         print(f"✅ TTS Success ({len(audio_data)} bytes)")

#         return audio_data

#     except Exception:
#         print("========== TTS ERROR ==========")
#         traceback.print_exc()
#         raise


# async def _text_to_speech(text: str) -> bytes:
#     return await asyncio.to_thread(_text_to_speech_sync, text)


# =========================
# STT
# =========================
def _speech_to_text(audio_bytes: bytes) -> str:
    whisper = get_whisper()

    with tempfile.NamedTemporaryFile(
        suffix=".webm",
        delete=False
    ) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        print("Starting transcription...")
        print("Before transcribe")

        segments, info = whisper.transcribe(
            tmp_path,
            language="ar",
            beam_size=1
        )

        print("After transcribe")

        texts = []

        for segment in segments:
            print("Segment:", segment.text)
            texts.append(segment.text)

        text = " ".join(texts).strip()

        print("Transcript:", text)

        return text

    except Exception:
        print("========== STT ERROR ==========")
        traceback.print_exc()
        raise

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# =========================
# RAG / LLM
# =========================

async def get_answer(question: str) -> str:
    print("Question:", question)

    answer = await asyncio.to_thread(
        rag.answer_question,
        question
    )

    print("Answer:", answer)

    return answer
# =========================
# Models
# =========================

class TTSRequest(BaseModel):
    text: str


# =========================
# Health
# =========================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


# =========================
# Chat
# =========================

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    try:
        answer = await get_answer(request.message)

        return ChatResponse(answer=answer)

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Chat failed"
        )


# =========================
# TTS Endpoint
# =========================

@router.post("/tts")
async def tts_endpoint(request: TTSRequest):
    try:
        audio_data = await _text_to_speech(request.text)

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg"
        )

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="TTS Failed"
        )


# =========================
# Voice Endpoint
# =========================

# @router.post("/voice")
# async def voice(audio: UploadFile = File(...)):
#     try:
#         print("Voice request received")

#         audio_bytes = await audio.read()

#         question = await asyncio.to_thread(
#             _speech_to_text,
#             audio_bytes
#         )

#         if not question:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Could not transcribe audio"
#             )

#         answer_text = await asyncio.to_thread(
#             rag.answer_question,
#             question
#         )

#         audio_data = await _text_to_speech(
#             answer_text
#         )

#         return StreamingResponse(
#             io.BytesIO(audio_data),
#             media_type="audio/mpeg",
#             headers={
#                 "X-Answer-Text": answer_text[:500]
#             }
#         )

#     except HTTPException:
#         raise

#     except Exception:
#         traceback.print_exc()

#         raise HTTPException(
#             status_code=500,
#             detail="Voice Failed"
#         )
@router.post("/voice")
async def voice(audio: UploadFile = File(...)):
    try:
        audio_bytes = await audio.read()

        question = await asyncio.to_thread(
            _speech_to_text,
            audio_bytes
        )

        if not question:
            raise HTTPException(
                status_code=400,
                detail="Could not transcribe audio"
            )

        answer_text = await get_answer(question)

        return {
            "transcript": question,
            "answer": answer_text
        }

    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Voice Failed"
        )
