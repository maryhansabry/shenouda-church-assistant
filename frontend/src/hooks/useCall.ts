import { useState, useRef, useCallback } from 'react';
import type {
  SpeechRecognition,
  SpeechRecognitionEvent,
  SpeechRecognitionErrorEvent,
} from '../types/speech';
import { stripOverlap } from '../utils/stripOverlap';

export type CallStatus =
  | 'idle'
  | 'connecting'
  | 'listening'   // المايك فاتح، بيسجل كلام المستخدم محليًا (Web Speech API)
  | 'processing'  // المستخدم خلص كلامه، السيرفر بيعالج (LLM) قبل الرد
  | 'speaking'    // صوت رد المساعد بيتشغل
  | 'error';

interface UseCallOptions {
  onTranscript: (text: string) => void;   // اللي المستخدم قاله
  onAnswer: (text: string) => void;        // رد المساعد النصي
}

interface UseCallReturn {
  status: CallStatus;
  startCall: () => void;
  endCall: () => void;
  toggleMic: () => void; // ابدأ الكلام / خلصت الكلام (زي زرار تسجيل/إرسال الفويس نوت)
  isMicMuted: boolean;
  isCallActive: boolean;
  errorMsg: string | null;
}

const WS_URL =
  (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/^http/, 'ws') +
  '/ws/call';

const PLAYBACK_SAMPLE_RATE = 24000; // نفس sample rate صوت Gemini TTS الراجع

// أخطاء مؤقتة/غير قاتلة بنتجاهلها ونعيد المحاولة من غير ما نقفل الجلسة
const RECOVERABLE_ERRORS = new Set(['no-speech', 'audio-capture', 'network']);

// المدة اللي لازم تعدي من غير نص حقيقي جديد عشان نعتبر إن المستخدم خلص كلامه
// تلقائيًا (auto end-of-turn) - بديل لضغطة زرار "خلصت الكلام" اليدوية
const SILENCE_AUTOSEND_MS = 1200;

// أقل طول نص (بعد trim) نعتبره كلام حقيقي - أقصر من كده بيتجاهل
// (همسة/نفس/نويز بيرجع أحيانًا كـ isFinal بنص تافه أو حرف واحد)
const MIN_VALID_CHUNK_LENGTH = 2;

/**
 * Manages a WebSocket-based real-time voice call with the assistant.
 *
 * التعرف على الصوت (STT) بيحصل بالكامل في المتصفح عبر Web Speech API
 * (نفس المحرك اللي بيستخدمه زرار الفويس نوت في الشات العادي)، مش عبر
 * بث صوت خام للسيرفر - ده بيدّي جودة تعرف أعلى بكتير من أي موديل
 * Whisper محلي، خصوصًا مع اللهجة المصرية.
 *
 * الفكرة: زرار واحد - "ابدأ الكلام" (unmute) / "خلصت الكلام" (mute):
 *  - ابدأ الكلام: بيشغّل SpeechRecognition من جديد. لو المساعد كان لسه
 *    بيتكلم أو بيعالج، ده يعتبر مقاطعة (barge-in) - بنوقف صوته فورًا
 *    محليًا وبنبلغ السيرفر يلغي أي رد شغال.
 *  - خلصت الكلام: بيوقف SpeechRecognition، وبمجرد ما يوصل النص النهائي
 *    بنبعته كـ نص جاهز للسيرفر (مش صوت) عشان يبدأ LLM -> TTS على طول.
 *
 * فوق ده، وإحنا لسه unmuted، فيه auto end-of-turn: لو عدت SILENCE_AUTOSEND_MS
 * من غير أي نص حقيقي جديد، بنبعت النص المتجمع تلقائيًا من غير ما نستنى
 * ضغطة الزرار - الزرار اليدوي (toggleMic) لسه شغال زي ما هو بالظبط
 * كطريقة بديلة/يدوية لإنهاء الدور في أي وقت.
 *
 * المايك بيبدأ مقفول (muted) بشكل افتراضي لحظة ما الكول يتصل: الـ
 * WebSocket بيتفتح ومفيش SpeechRecognition شغال لحد ما المستخدم يدوس
 * "ابدأ الكلام" (toggleMic) بنفسه - ده اللي بيستدعي startRecognition()
 * ويبلغ السيرفر بـ start_turn.
 */
export function useCall({ onTranscript, onAnswer }: UseCallOptions): UseCallReturn {
  const [status, setStatus] = useState<CallStatus>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isMicMuted, setIsMicMuted] = useState(true);

  const wsRef = useRef<WebSocket | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const transcriptBufferRef = useRef<string>('');   // بيجمع كل النص لحد "خلصت الكلام"
  const isStoppingRef = useRef<boolean>(false);     // لتفرقة الإيقاف اليدوي عن التوقف التلقائي
  const restartTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // آخر index اتعالج فعليًا كـ isFinal جوه الجلسة الحالية (بيتصفر مع كل session جديدة/restart)
  const lastFinalIndexRef = useRef<number>(-1);

  // تايمر السكوت لـ auto end-of-turn - بيتصفر بس لما يوصل نص حقيقي جديد
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const playbackContextRef = useRef<AudioContext | null>(null);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextStartTimeRef = useRef(0);

  // بيتفعل وقت ما لحن/رابط صوت جاهز (زي ترحيب البابا) شغال - بيمنع
  // "answer_audio_end" (اللي بيوصل فورًا بعد ما نبعت play_url) من إنه
  // يقفل الـ status بدري قبل ما اللحن يخلص فعليًا (source.onended)
  const isPlayingUrlRef = useRef(false);

  const clearRestartTimeout = () => {
    if (restartTimeoutRef.current) {
      clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
  };

  const clearSilenceTimer = () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  };

  /** بتوقف أي صوت شغال أو متجدول للمساعد فورًا (استخدامها الأساسي: barge-in) */
  const stopPlayback = useCallback(() => {
    for (const source of activeSourcesRef.current) {
      try {
        source.stop();
      } catch {
        // ممكن يكون خلص أصلاً - نتجاهل
      }
    }
    activeSourcesRef.current = [];

    if (playbackContextRef.current) {
      nextStartTimeRef.current = playbackContextRef.current.currentTime;
    }

    // كانت هنا مراجعة لـ urlAudioRef (عنصر <audio> غير موجود أصلاً في
    // الكود ده) - بقينا بنشغل روابط الصوت عبر نفس الـ AudioContext
    // زي أي source تاني، فبيتوقف مع الحلقة اللي فوق. بنصفّر الـ flag بس.
    isPlayingUrlRef.current = false;
  }, []);

  /** بتاخد شريحة صوت PCM16 خام (24kHz) وتضيفها لطابور التشغيل المتصل */
  const scheduleAudioChunk = useCallback((buffer: ArrayBuffer) => {
    const playbackContext = playbackContextRef.current;
    if (!playbackContext) return;

    const int16 = new Int16Array(buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
    }

    const audioBuffer = playbackContext.createBuffer(
      1,
      float32.length,
      PLAYBACK_SAMPLE_RATE
    );
    audioBuffer.copyToChannel(float32, 0);

    const source = playbackContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(playbackContext.destination);

    const startTime = Math.max(playbackContext.currentTime, nextStartTimeRef.current);
    source.start(startTime);
    nextStartTimeRef.current = startTime + audioBuffer.duration;

    activeSourcesRef.current.push(source);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
    };
  }, []);

  /** بتشغّل رابط صوت جاهز (MP3 من Cloudinary مثلاً، زي لحن الترحيب) عبر
   *  نفس الـ AudioContext المفتوح أصلاً للمكالمة - مش عنصر <audio> جديد
   *  منفصل، عشان نتجنب قيود الـ autoplay على الموبايل اللي بتمنع تشغيل
   *  عنصر <audio> جديد من غير user gesture مباشر مرتبط بيه. */
  const playAudioUrl = useCallback(async (url: string) => {
    stopPlayback();

    const playbackContext = playbackContextRef.current;
    if (!playbackContext) {
      console.error('No playback context available to play hymn URL');
      setStatus('listening');
      return;
    }

    setStatus('speaking');
    isPlayingUrlRef.current = true;

    try {
      if (playbackContext.state === 'suspended') {
        await playbackContext.resume();
      }

      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const audioBuffer = await playbackContext.decodeAudioData(arrayBuffer);

      const source = playbackContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(playbackContext.destination);

      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
        isPlayingUrlRef.current = false;
        setStatus('listening');
      };

      const startTime = Math.max(playbackContext.currentTime, nextStartTimeRef.current);
      activeSourcesRef.current.push(source);
      source.start(startTime);
      nextStartTimeRef.current = startTime + audioBuffer.duration;
    } catch (err) {
      console.error('Failed to play hymn URL:', url, err);
      isPlayingUrlRef.current = false;
      setStatus('listening');
    }
  }, [stopPlayback]);

  /** بتاخد النص النهائي اللي اتجمع وتبعته للسيرفر كـ نص جاهز (مش صوت) */
  const sendFinalTranscript = useCallback(() => {
    clearSilenceTimer();

    const text = transcriptBufferRef.current.trim();
    transcriptBufferRef.current = '';

    if (!text) return;

    onTranscript(text);

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'user_text', text }));
    }
  }, [onTranscript]);

  /** بتبدأ جلسة SpeechRecognition جديدة (نفس منطق useVoice.ts) */
  const startRecognition = useCallback(() => {
    transcriptBufferRef.current = '';
    isStoppingRef.current = false;
    lastFinalIndexRef.current = -1;
    clearRestartTimeout();
    clearSilenceTimer();

    const SpeechRecognitionImpl =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionImpl) {
      setErrorMsg('المتصفح لا يدعم التعرف على الصوت');
      setStatus('error');
      return;
    }

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = 'ar-EG';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => setStatus('listening');

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const startIndex = Math.max(event.resultIndex, lastFinalIndexRef.current + 1);

      let finalChunk = '';
      for (let i = startIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalChunk += result[0].transcript;
          lastFinalIndexRef.current = i;
        }
      }

      if (finalChunk) {
        const deduped = stripOverlap(transcriptBufferRef.current, finalChunk);
        // تجاهل النص لو أقصر من MIN_VALID_CHUNK_LENGTH (همسة/نويز بيرجع
        // أحيانًا كـ isFinal بنص تافه) - مبيصفرش تايمر السكوت
        if (deduped && deduped.trim().length >= MIN_VALID_CHUNK_LENGTH) {
          transcriptBufferRef.current += deduped + ' ';

          // نص حقيقي وصل - صفّر تايمر السكوت وابدأه من جديد
          clearSilenceTimer();
          silenceTimerRef.current = setTimeout(() => {
            sendFinalTranscript();
          }, SILENCE_AUTOSEND_MS);
        }
      }
    };

    let fatalError = false;

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (RECOVERABLE_ERRORS.has(event.error)) {
        return;
      }
      fatalError = true;
      isStoppingRef.current = true;
      clearSilenceTimer();
      setErrorMsg('تعذر التعرف على الصوت');
      setStatus('error');
    };

    recognition.onend = () => {
      if (!isStoppingRef.current && !fatalError) {
        clearRestartTimeout();
        restartTimeoutRef.current = setTimeout(() => {
          try {
            lastFinalIndexRef.current = -1;
            recognition.start();
          } catch {
            sendFinalTranscript();
          }
        }, 0);
        return;
      }

      sendFinalTranscript();
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [sendFinalTranscript]);

  const startCall = useCallback(async () => {
    if (
      wsRef.current !== null ||
      status === 'connecting' ||
      status === 'listening' ||
      status === 'processing' ||
      status === 'speaking'
    ) {
      console.warn('Call already active or connecting — ignoring duplicate startCall');
      return;
    }

    setErrorMsg(null);
    setStatus('connecting');
    setIsMicMuted(true);

    // بننشئ الـ AudioContext ونعمله resume هنا فورًا - جوه نفس الـ call
    // stack المتزامن بتاع ضغطة المستخدم على الزرار (قبل أي await لفتح
    // الـ WebSocket). ده ضروري على iOS Safari وبعض متصفحات الموبايل
    // عشان الصوت يتحسب "unlocked" فعليًا ولو اتشغل بعدين بشكل غير متزامن
    // (زي لحن الترحيب اللي بيوصل عبر رسالة WebSocket لاحقة).
    try {
      playbackContextRef.current = new AudioContext({
        sampleRate: PLAYBACK_SAMPLE_RATE,
      });
      await playbackContextRef.current.resume();
      nextStartTimeRef.current = 0;
    } catch {
      setErrorMsg('لا يمكن تفعيل الصوت على هذا الجهاز.');
      setStatus('error');
      return;
    }

    try {
      const ws = new WebSocket(WS_URL);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        // المايك مقفول بشكل افتراضي - متبدأش SpeechRecognition لوحدها.
        // المستخدم لازم يدوس "ابدأ الكلام" (toggleMic) عشان يشغّلها.
      };

      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data === 'string') {
          const msg = JSON.parse(event.data);

          switch (msg.type) {
            case 'interrupted':
              stopPlayback();
              setStatus('listening');
              break;

            case 'processing':
              setStatus('processing');
              break;

            case 'answer_text':
              onAnswer(msg.text as string);
              break;

            case 'answer_audio_start':
              setStatus('speaking');
              break;

            case 'answer_audio_end':
              // لو لحن/رابط صوت جاهز شغال دلوقتي (زي ترحيب البابا)،
              // متسبقهوش تقفل الـ status - onended بتاعه هو اللي يقرر
              if (!isPlayingUrlRef.current) {
                setStatus('listening');
              }
              break;

            case 'play_url':
              playAudioUrl(msg.url as string);
              break;

            case 'error':
              setErrorMsg(msg.message as string);
              setStatus('error');
              break;
          }
        } else {
          scheduleAudioChunk(event.data as ArrayBuffer);
        }
      };

      ws.onerror = () => {
        setErrorMsg('تعذر الاتصال بالخادم.');
        setStatus('error');
      };

      ws.onclose = () => {
        setStatus((prev) => (prev === 'idle' ? prev : 'idle'));
      };
    } catch {
      setErrorMsg('تعذر بدء المكالمة.');
      setStatus('error');
    }
  }, [status, onAnswer, scheduleAudioChunk, stopPlayback, playAudioUrl]);

  const endCall = useCallback(() => {
    stopPlayback();

    isStoppingRef.current = true;
    clearRestartTimeout();
    clearSilenceTimer();
    recognitionRef.current?.stop();
    recognitionRef.current = null;

    playbackContextRef.current?.close();
    playbackContextRef.current = null;

    wsRef.current?.close();
    wsRef.current = null;

    setStatus('idle');
    setErrorMsg(null);
    setIsMicMuted(true);
  }, [stopPlayback]);

  /** زرار واحد بيتحكم في كل حاجة - زي زرار تسجيل/إرسال الفويس نوت:
   *  - بيدوس يبدأ يتكلم (unmute): بيشغّل SpeechRecognition من جديد. لو
   *    المساعد كان بيتكلم لسه، ده يعتبر مقاطعة (barge-in) - بنوقف صوته
   *    فورًا محليًا وبنبلغ السيرفر.
   *  - بيدوس تاني لما يخلص كلامه (mute): بيوقف SpeechRecognition، وبمجرد
   *    ما يوصل النص النهائي بيتبعت للسيرفر كنص جاهز (STT خلص في المتصفح).
   *
   *  ده لسه شغال بالظبط زي ما هو - المستخدم يقدر يدوس "خلصت الكلام" في
   *  أي وقت من غير ما يستنى تايمر السكوت. تايمر السكوت (auto-send) ده
   *  طبقة إضافية بس فوق نفس المنطق، مش بديل ليه.
   */
  const toggleMic = useCallback(() => {
    const goingToMuted = !isMicMuted;
    setIsMicMuted(goingToMuted);

    if (goingToMuted) {
      // خلص كلامه - أوقفي SpeechRecognition؛ onend هيبعت النص تلقائيًا
      isStoppingRef.current = true;
      clearRestartTimeout();
      clearSilenceTimer();
      recognitionRef.current?.stop();
    } else {
      // بدأ يتكلم من جديد - وقفي أي صوت شغال محليًا فورًا وبلغي السيرفر
      stopPlayback();
      setStatus('listening');
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'start_turn' }));
      }
      startRecognition();
    }
  }, [isMicMuted, stopPlayback, startRecognition]);

  return {
    status,
    startCall,
    endCall,
    toggleMic,
    isMicMuted,
    isCallActive: status !== 'idle',
    errorMsg,
  };
}
