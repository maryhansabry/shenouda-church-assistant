import { useState, useRef, useCallback } from 'react';
import type {
  SpeechRecognition,
  SpeechRecognitionEvent,
  SpeechRecognitionErrorEvent,
} from '../types/speech';
// import { sendVoice } from '../services/api';

interface UseVoiceReturn {
  isRecording: boolean;
  isProcessing: boolean;
  startRecording: () => void;
  stopRecording: () => void;
  error: string | null;
}

import { stripOverlap } from '../utils/stripOverlap';

// أخطاء مؤقتة/غير قاتلة بنتجاهلها ونعيد المحاولة من غير ما نقفل الجلسة
const RECOVERABLE_ERRORS = new Set(['no-speech', 'audio-capture', 'network']);

export function useVoice(onAnswer: (text: string) => void): UseVoiceReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const transcriptBufferRef = useRef<string>('');   // بيجمع كل النص لحد الإيقاف
  const isStoppingRef = useRef<boolean>(false);     // لتفرقة الإيقاف اليدوي عن التوقف التلقائي
  const restartTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // آخر index اتعالج فعليًا كـ isFinal جوه الجلسة الحالية (بيتصفر مع كل session جديدة/restart)
  // ده بيمنع تكرار النص لو المتصفح رجّع نفس الـ resultIndex أو index أقل تاني (باج معروف في Chrome)
  const lastFinalIndexRef = useRef<number>(-1);

  const clearRestartTimeout = () => {
    if (restartTimeoutRef.current) {
      clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
  };

  const startRecording = useCallback(() => {
    setError(null);
    transcriptBufferRef.current = '';
    isStoppingRef.current = false;
    lastFinalIndexRef.current = -1;
    clearRestartTimeout();

    const SpeechRecognitionImpl =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionImpl) {
      setError('المتصفح لا يدعم التعرف على الصوت');
      return;
    }

    const recognition = new SpeechRecognitionImpl();
    recognition.lang = 'ar-EG';
    recognition.continuous = true;      // يفضل شغال لحد ما توقفيه
    recognition.interimResults = true;  // عشان يفضل يبعت partial results ومايقفلش لوحده

    recognition.onstart = () => setIsRecording(true);

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      // بنبدأ من أكبر قيمة بين اللي المتصفح بيقوله (resultIndex) واللي إحنا فعليًا
      // وصلنا له قبل كده، عشان مانعالجش نفس الـ index مرتين لو المتصفح رجّعه تاني
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
        if (deduped) {
          transcriptBufferRef.current += deduped + ' ';
        }
      }
    };

    // بنسجل هل الخطأ ده لازم يقفل الجلسة نهائي ولا نتجاهله ونسيب onend يعيد المحاولة
    let fatalError = false;

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (RECOVERABLE_ERRORS.has(event.error)) {
        // مش قاتل - onend هيتنفذ بعده وهيعيد المحاولة عادي، من غير ما نقفل التسجيل
        return;
      }
      fatalError = true;
      isStoppingRef.current = true; // امنع أي إعادة تشغيل تلقائية
      setError('تعذر التعرف على الصوت');
      setIsRecording(false);
    };

    recognition.onend = () => {
      // لو المستخدم لسه مدوسش إيقاف، وملقيناش خطأ قاتل: إعادة التشغيل تلقائيًا
      // من غير ما نطفي isRecording (تجنبًا لفليكر الواجهة)
      if (!isStoppingRef.current && !fatalError) {
        clearRestartTimeout();
        // تأخير بسيط بيدي فرصة للمتصفح يصفّر حالته الداخلية
        // قبل ما نحاول start() تاني - بيقلل احتمال InvalidStateError
        restartTimeoutRef.current = setTimeout(() => {
          try {
            lastFinalIndexRef.current = -1; // session جديدة هتبدأ results من الأول
            recognition.start();
          } catch {
            // فشلت إعادة المحاولة فعلاً - اعتبرها نهاية حقيقية
            finalizeSession();
          }
        }, 250);
        return;
      }

      finalizeSession();
    };

    const finalizeSession = () => {
      setIsRecording(false);

      const text = transcriptBufferRef.current.trim();
      transcriptBufferRef.current = '';
      isStoppingRef.current = false;

      if (text) {
        setIsProcessing(true);
        Promise.resolve(onAnswer(text)).finally(() => {
          setIsProcessing(false);
        });
      }
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [onAnswer]);

  const stopRecording = useCallback(() => {
    isStoppingRef.current = true;
    clearRestartTimeout();
    recognitionRef.current?.stop();
  }, []);

  return { isRecording, isProcessing, startRecording, stopRecording, error };
}
