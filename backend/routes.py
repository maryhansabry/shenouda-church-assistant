import io
import json
import base64
import asyncio
import tempfile
import os
import traceback
import wave

import numpy as np
import httpx

from fastapi import APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from faster_whisper import WhisperModel

from models import ChatRequest, ChatResponse, HealthResponse, HistoryItem
from config import (
    WHISPER_MODEL,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    GEMINI_API_KEY,
    GEMINI_TTS_MODEL,
    GEMINI_TTS_VOICE,
    GEMINI_TTS_STYLE_PROMPT,
    GROQ_API_KEY,
    GROQ_STT_MODEL,
)
import rag

router = APIRouter()

# =========================
# إعدادات المكالمة الفورية (Real-time call)
# =========================

CALL_SAMPLE_RATE = 16000

MIN_UTTERANCE_MS = 1000
MIN_UTTERANCE_BYTES = int(CALL_SAMPLE_RATE * MIN_UTTERANCE_MS / 1000) * 2

MIN_SPEECH_RMS = 500.0


def _is_too_quiet(pcm_bytes: bytes) -> bool:
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if audio.size == 0:
        return True
    rms = float(np.sqrt(np.mean(np.square(audio))))
    return rms < MIN_SPEECH_RMS


GEMINI_TTS_SAMPLE_RATE = 24000
GEMINI_AUDIO_CHUNK_BYTES = 4800

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


# عتبات لرفض segments مهلوسة (نص بيطلع من ويسبر على سكوت/ضوضاء
# مش كلام فعلي) - نفس الظاهرة اللي شفناها في اللوج مع Groq، ممكن
# تحصل مع أي موديل ويسبر لو الصوت مش واضح
MAX_NO_SPEECH_PROB = 0.6
MIN_AVG_LOGPROB = -1.6


def _speech_to_text_pcm(pcm_bytes: bytes) -> str:
    whisper = get_whisper()

    audio_array = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    segments, _ = whisper.transcribe(
        audio_array,
        language="ar",
        beam_size=5,
        # بيدي الموديل تلميح عن مفردات الدومين (أسماء كنسية) - بيحسّن
        # فرصة التعرف الصح عليها عند tiny تحديدًا
        initial_prompt="كنيسة الأنبا شنودة، الأب الكاهن، القمص، الأنبا، البابا تواضروس، الاعتراف، القداس، مدارس الأحد",
        # من غير كده، الموديل بيميل يكرر آخر جملة/كلمة في حلقة لانهائية
        # (زي "أحل أنا أحل أنا أحل أنا...") لما يبقى غير متأكد من الصوت -
        # دي أشهر أسباب التهلوس مع الموديلات الصغيرة
        condition_on_previous_text=False,
        # فلترة داخلية للسكوت جوه الـ utterance نفسها قبل ما يحاول يفسرها كلام
        vad_filter=True,
    )

    texts = []
    for segment in segments:
        if segment.no_speech_prob > MAX_NO_SPEECH_PROB or segment.avg_logprob < MIN_AVG_LOGPROB:
            print(
                f"Rejected hallucinated segment (no_speech_prob={segment.no_speech_prob:.2f}, "
                f"avg_logprob={segment.avg_logprob:.2f}): {segment.text!r}"
            )
            continue
        texts.append(segment.text)

    text = " ".join(texts).strip()

    print("Call transcript (local whisper):", text)

    return text


async def _speech_to_text_groq(pcm_bytes: bytes) -> str:
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(CALL_SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    wav_buffer.seek(0)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.wav", wav_buffer, "audio/wav")},
            data={
                "model": GROQ_STT_MODEL,
                "language": "ar",
            },
        )

        if resp.status_code != 200:
            print("========== GROQ STT ERROR ==========")
            print("STATUS:", resp.status_code)
            print("BODY:", resp.text)
            resp.raise_for_status()

        text = resp.json().get("text", "").strip()

    print("Call transcript (Groq):", text)
    return text


GEMINI_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TTS_MODEL}:generateContent"
)

# نص افتراضي بديل بيتقال بالـ TTS لما Gemini يحجب الرد الأصلي (نادر،
# لكنه بيحصل غلط مع بعض الألقاب الدينية). بيمنع سقوط المكالمة بالكامل.
GEMINI_TTS_FALLBACK_TEXT = "تم إعداد الإجابة، برجاء قراءتها في الشات."


def _build_gemini_tts_payload(text: str) -> dict:
    styled_text = f"{GEMINI_TTS_STYLE_PROMPT}\n\n{text}"

    return {
        "contents": [{"parts": [{"text": styled_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}
                }
            },
        },
        # الفلتر الافتراضي بيدّي false-positive أحيانًا مع ألقاب دينية
        # عادية (أبونا، القمص، الأنبا...) وبيرجع PROHIBITED_CONTENT من
        # غير أي سبب واضح. بنخفف الفلتر هنا لأن المحتوى كله نصوص كنسية
        # آمنة تمامًا.
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }


async def _gemini_text_to_speech(text: str) -> bytes | None:
    """بترجع bytes الصوت (PCM16 خام) أو None لو Gemini حجب المحتوى أو
    رجّع استجابة غير متوقعة (زي blockReason من غير candidates).

    مهم: أي كود بيستدعيها لازم يتعامل مع رجوع None بشكل صريح (يكمل
    من غير صوت، أو يجرب fallback نص بديل) بدل ما يفترض إنها هترجع
    صوت دايمًا - وإلا الطلب كله (chat/voice/call) هيقع بسبب حجب TTS
    مش له علاقة بصحة الإجابة نفسها."""
    print("ENTERED GEMINI TTS")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            GEMINI_TTS_URL,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=_build_gemini_tts_payload(text),
        )

        if resp.status_code != 200:
            print("========== GEMINI TTS ERROR ==========")
            print("STATUS:", resp.status_code)
            print("BODY:", resp.text)

        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates")

    if not candidates:
        block_reason = data.get("promptFeedback", {}).get("blockReason")
        print("========== GEMINI TTS BLOCKED / EMPTY ==========")
        print("Block reason:", block_reason, "| text_len:", len(text))
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return None

    try:
        b64_audio = candidates[0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError):
        print("========== GEMINI TTS UNEXPECTED RESPONSE ==========")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return None

    return base64.b64decode(b64_audio)


async def _gemini_text_to_speech_with_fallback(text: str) -> bytes | None:
    """زي _gemini_text_to_speech لكن لو النص الأصلي اتحجب، بتجرب مرة
    واحدة بنص بديل عام آمن بدل ما ترجع None على طول. مفيدة في مسار
    المكالمة حيث لازم نرجّع صوت ما مهما كان."""
    audio = await _gemini_text_to_speech(text)
    if audio is not None:
        return audio

    print("Retrying Gemini TTS with fallback text after block...")
    return await _gemini_text_to_speech(GEMINI_TTS_FALLBACK_TEXT)

# =========================
# RAG / LLM
# =========================

async def get_answer(
    question: str, history: list[HistoryItem] | None = None
) -> tuple[str, list[str], str | None]:
    """بترجع (answer, images, audio_url). audio_url بيبقى None في الحالات
    العادية، وبيتحدد بس لما تريجر خاص (زي ترحيب البابا) يشتغل في
    rag.answer_question ويرجع رابط صوت جاهز بدل ما يمر على الـ LLM."""
    print("Question:", question)

    history_dicts = [item.model_dump() for item in history] if history else []

    answer, images, audio_url = await asyncio.to_thread(
        rag.answer_question,
        question,
        history_dicts
    )

    print("Answer:", answer)
    if images:
        print("Images:", images)
    if audio_url:
        print("Audio URL:", audio_url)

    return answer, images, audio_url


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
# Debug - مؤقت، نشيله بعد ما نحل مشكلة الصوت
# =========================

@router.get("/debug/last-call-audio")
async def debug_last_call_audio():
    path = "/tmp/last_call_utterance.wav"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No call audio recorded yet")
    return FileResponse(path, media_type="audio/wav", filename="last_call_utterance.wav")


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
        answer, images, audio_url = await get_answer(request.message, request.history)

        return ChatResponse(answer=answer, images=images, audio_url=audio_url)

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
        audio_data = await _gemini_text_to_speech(request.text)

        if audio_data is None:
            # اتحجب من Gemini (أو رجّع استجابة غير متوقعة) - مش خطأ سيرفر
            # فعلي، فبنرجّع 422 واضحة بدل 500 عشان العميل يقدر يفرّق بينهم
            raise HTTPException(
                status_code=422,
                detail="Text-to-speech was blocked or returned no audio for this text"
            )

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type="audio/pcm"
        )
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="TTS Failed"
        )


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

        answer_text, images, audio_url = await get_answer(question)

        return {
            "transcript": question,
            "answer": answer_text,
            "images": images,
            "audio_url": audio_url,
        }

    except Exception:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Voice Failed"
        )


# =========================
# Real-time Call (WebSocket)
# =========================
#
# بروتوكول المكالمة الفورية بين العميل (useCall.ts) والسيرفر ده:
#
# Client → Server:
#   - {"type": "user_text", "text": "..."}   المستخدم خلص كلامه، والنص
#     ده جاهز فعلاً (اتعرّف عليه في المتصفح بـ Web Speech API - مفيش
#     STT جوه السيرفر تاني لمسار المكالمة)
#   - {"type": "start_turn"}   المستخدم بدأ يتكلم من جديد (ممكن تكون
#     مقاطعة/barge-in لو كان في رد شغال)
#
# Server → Client:
#   - {"type": "interrupted"}
#   - {"type": "processing"}
#   - {"type": "answer_text", "text": "..."}
#   - {"type": "answer_audio_start"}
#   - Binary frames: صوت PCM16 خام 24kHz mono على شرائح ~100ms
#   - {"type": "answer_audio_end"}
#   - {"type": "play_url", "url": "..."}   جديد: لما الرد عبارة عن رابط
#     صوت جاهز (زي لحن ترحيب البابا) بدل PCM متولّد من TTS - العميل
#     يشغّله مباشرة بـ Audio API عادي، مش عبر مسار الـ PCM streaming.
#   - {"type": "answer_audio_skipped"}   جديد: التوليد الصوتي اتحجب حتى
#     بعد إعادة المحاولة بنص بديل - العميل يعرض النص بس من غير صوت.


async def _process_question(
    websocket: WebSocket,
    question: str,
    call_state: dict,
) -> None:
    try:
        await websocket.send_json({"type": "processing"})

        answer_text, images, audio_url = await get_answer(question)

        if images:
            await websocket.send_json({"type": "images", "images": images})

        await websocket.send_json({"type": "answer_text", "text": answer_text})

        # لو فيه رابط صوت جاهز (تريجر خاص زي ترحيب البابا)، لازم الأول
        # نقول نص الترحيب فعليًا بالـ TTS العادي، وبس بعد ما ينتهي فعليًا
        # (مش مجرد بعد ما نبعت آخر chunk) نبعت play_url للحن. لو بعتنا
        # play_url بدري، playAudioUrl في العميل بيعمل stopPlayback() أول
        # حاجة، وده هيقطع صوت الترحيب لو لسه بيتشغل فعليًا عند العميل.
        if audio_url:
            greeting_audio = await _gemini_text_to_speech_with_fallback(answer_text)

            if greeting_audio is None:
                # اتحجب حتى مع الـ fallback - نكمل على play_url على طول
                # من غير صوت ترحيب، بدل ما نوقف الرد بالكامل
                print("Greeting TTS blocked even with fallback - skipping to play_url")
                await websocket.send_json({"type": "answer_audio_skipped"})
                await websocket.send_json({"type": "play_url", "url": audio_url})
                return

            print("Greeting audio bytes:", len(greeting_audio))

            await websocket.send_json({"type": "answer_audio_start"})
            call_state["speaking"] = True

            for i in range(0, len(greeting_audio), GEMINI_AUDIO_CHUNK_BYTES):
                chunk = greeting_audio[i:i + GEMINI_AUDIO_CHUNK_BYTES]
                await websocket.send_bytes(chunk)
                await asyncio.sleep(0)

            await websocket.send_json({"type": "answer_audio_end"})

            # مدة صوت الترحيب الفعلية (samples / sample_rate) - بننتظرها
            # عشان نضمن إن التشغيل عند العميل خلص فعلاً قبل ما نبعت
            # play_url، لأن playAudioUrl بتعمل stopPlayback() أول حاجة
            num_samples = len(greeting_audio) // 2  # PCM16 = 2 bytes/sample
            greeting_duration = num_samples / GEMINI_TTS_SAMPLE_RATE
            await asyncio.sleep(greeting_duration)

            await websocket.send_json({"type": "play_url", "url": audio_url})
            return

        audio_data = await _gemini_text_to_speech_with_fallback(answer_text)

        if audio_data is None:
            # اتحجب حتى مع الـ fallback - المستخدم لسه شايف النص (answer_text
            # اتبعت فوق بالفعل)، بس من غير صوت. أهم حاجة إن المكالمة
            # تكمل من غير ما تقع
            print("Answer TTS blocked even with fallback - skipping audio")
            await websocket.send_json({"type": "answer_audio_skipped"})
            return

        print("Audio bytes:", len(audio_data))

        await websocket.send_json({"type": "answer_audio_start"})
        call_state["speaking"] = True

        for i in range(0, len(audio_data), GEMINI_AUDIO_CHUNK_BYTES):
            chunk = audio_data[i:i + GEMINI_AUDIO_CHUNK_BYTES]
            await websocket.send_bytes(chunk)
            await asyncio.sleep(0)

        await websocket.send_json({"type": "answer_audio_end"})

    except asyncio.CancelledError:
        raise

    except Exception:
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": "حصل خطأ أثناء معالجة الرد"
            })
        except Exception:
            pass

    finally:
        call_state["speaking"] = False


@router.websocket("/ws/call")
async def call_websocket(websocket: WebSocket):
    await websocket.accept()

    current_task: asyncio.Task | None = None
    call_state = {"speaking": False}

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if message.get("text") is not None:
                try:
                    control = json.loads(message["text"])
                except (TypeError, json.JSONDecodeError):
                    continue

                msg_type = control.get("type")

                if msg_type == "user_text":
                    # المستخدم خلص كلامه، والنص جاهز فعلاً (Web Speech API
                    # في المتصفح) - نبدأ المعالجة (LLM -> TTS) على طول
                    question = (control.get("text") or "").strip()

                    if not question:
                        continue

                    if current_task is not None and not current_task.done():
                        print("Previous response still in progress - ignoring this utterance")
                        continue

                    print(f"Call question received: {question!r}")
                    current_task = asyncio.create_task(
                        _process_question(websocket, question, call_state)
                    )

                elif msg_type == "start_turn":
                    # المستخدم بدأ يتكلم من جديد - لو المساعد كان لسه بيتكلم
                    # أو بيعالج، ده barge-in فعلي: نلغي أي حاجة شغالة فورًا
                    if current_task is not None and not current_task.done():
                        print("Barge-in: cancelling in-progress response")
                        await websocket.send_json({"type": "interrupted"})
                        current_task.cancel()
                        current_task = None

                    call_state["speaking"] = False

                continue

            # مفيش بث صوت خام تاني في مسار المكالمة - التعرف على الصوت
            # بيحصل بالكامل في المتصفح (Web Speech API)، فأي bytes وصلت
            # هنا (لو حصل) بيتم تجاهلها

    except WebSocketDisconnect:
        pass

    finally:
        if current_task is not None and not current_task.done():
            current_task.cancel()
