import io
import json
import base64
import asyncio
import tempfile
import os
from fastapi import APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import edge_tts
from faster_whisper import WhisperModel

from models import ChatRequest, ChatResponse, HealthResponse
from config import TTS_VOICE, WHISPER_MODEL
import rag

router = APIRouter()

# Load Whisper once at import time
print(f"Loading Whisper model ({WHISPER_MODEL})...")
_whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="float32")
print("✅ Whisper ready")


async def _text_to_speech(text: str) -> bytes:
    """Convert text to MP3 bytes using edge-tts."""
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


def _speech_to_text(audio_bytes: bytes) -> str:
    """Transcribe audio bytes using faster-whisper."""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        segments, _ = _whisper.transcribe(tmp_path, language="ar")
        return " ".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(tmp_path)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        answer = await asyncio.to_thread(rag.answer_question, request.message)
        return ChatResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice")
async def voice(audio: UploadFile = File(...)):
    """One-shot voice: STT → RAG → TTS → return audio."""
    try:
        audio_bytes = await audio.read()

        # STT
        question = await asyncio.to_thread(_speech_to_text, audio_bytes)
        if not question:
            raise HTTPException(status_code=400, detail="Could not transcribe audio")

        # RAG
        answer_text = await asyncio.to_thread(rag.answer_question, question)

        # TTS
        audio_data = await _text_to_speech(answer_text)

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/mpeg",
            headers={"X-Answer-Text": answer_text[:500]},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/call")
async def realtime_call(websocket: WebSocket):
    """Real-time call: WebSocket-based STT → RAG → TTS loop."""
    await websocket.accept()
    audio_buffer: list[bytes] = []

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg["type"] == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg["type"] == "audio_chunk":
                audio_buffer.append(base64.b64decode(msg["data"]))

            elif msg["type"] == "end_of_speech":
                if not audio_buffer:
                    await websocket.send_text(json.dumps({"type": "error", "message": "No audio"}))
                    continue

                combined = b"".join(audio_buffer)
                audio_buffer.clear()

                # STT
                question = await asyncio.to_thread(_speech_to_text, combined)
                if not question:
                    await websocket.send_text(json.dumps({"type": "error", "message": "لم أفهم الصوت"}))
                    continue

                await websocket.send_text(json.dumps({"type": "transcript", "text": question}))

                # RAG
                answer_text = await asyncio.to_thread(rag.answer_question, question)
                await websocket.send_text(json.dumps({"type": "answer_done", "text": answer_text}))

                # TTS
                audio_data = await _text_to_speech(answer_text)
                chunk_size = 8192
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    await websocket.send_text(json.dumps({
                        "type": "audio_chunk",
                        "data": base64.b64encode(chunk).decode(),
                    }))
                await websocket.send_text(json.dumps({"type": "audio_done"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
