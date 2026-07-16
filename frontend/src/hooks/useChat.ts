import { useState, useCallback, useRef } from 'react';
import type { Message, HistoryItem } from '../types';
import { sendMessage } from '../services/api';

interface UseChatReturn {
  messages: Message[];
  isLoading: boolean;
  isSpeaking: boolean;
  error: string | null;
  sendUserMessage: (text: string) => Promise<void>;
  sendVoiceMessage: (text: string) => Promise<void>;
  addAssistantMessage: (text: string, images?: string[]) => void;
  addUserMessage: (text: string) => void;
  clearError: () => void;
}

// أقصى عدد رسائل (سؤال+رد) نبعتها كـ history مع كل طلب جديد
// عشان مانضخمش الـ payload ومانستهلكش توكنز زيادة عن اللزوم
const MAX_HISTORY_MESSAGES = 10;

/**
 * Manages the chat conversation state.
 * No TTS happens here at all — both typed messages and voice-note
 * messages get a TEXT-ONLY reply. TTS only happens inside the
 * real-time call flow (useCall.ts), which is full speech-to-speech.
 *
 * isSpeaking is always false here; it exists only to satisfy
 * components (like ChatWindow) that accept a shared "isSpeaking"
 * prop also used by the call flow.
 */
export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSpeaking = false;

  // نسخة مرآة (mirror) من messages بتتحدث فورًا (sync)، عشان send() يقدر
  // يبني الـ history من آخر حالة فعلية من غير ما يحتاج messages في dependency array
  // بتاعته (وده كان هيسبب إعادة إنشاء send() مع كل رسالة جديدة).
  const messagesRef = useRef<Message[]>([]);

  // حماية إضافية ضد إرسال مكرر (زي ضغطتين قريبتين جدًا على Enter، أو
  // "تكرار" لوحة المفاتيح التلقائي). بنستخدم ref مش state، لأن الـ ref
  // بيتحدّث فورًا (sync) - عكس isLoading (state) اللي بياخد وقت لحد ما
  // React يعمل render، وممكن الضغطة التانية "تشوفه" لسه false قبل ما
  // يتحدّث، فتعدي من غير قصد وتبعت طلب مكرر.
  const isSendingRef = useRef(false);

  const createMessage = (role: Message['role'], content: string, images?: string[]): Message => ({
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    role,
    content,
    timestamp: new Date(),
    images,
  });

  const appendMessage = useCallback((message: Message) => {
    setMessages((prev) => {
      const next = [...prev, message];
      messagesRef.current = next;
      return next;
    });
  }, []);

  const addAssistantMessage = useCallback(
    (text: string, images?: string[]) => {
      appendMessage(createMessage('assistant', text, images));
    },
    [appendMessage]
  );

  /** بتضيف رسالة المستخدم للشات بس - من غير ما تبعت طلب /chat جديد.
   * مستخدمة في المكالمة الفورية عشان السؤال أصلاً بيتعالج بالكامل عبر
   * WebSocket المكالمة نفسه. */
  const addUserMessage = useCallback(
    (text: string) => {
      appendMessage(createMessage('user', text));
    },
    [appendMessage]
  );

  const handleError = (err: unknown) => {
    const isNetworkError =
      err instanceof Error &&
      (err.message.includes('Network Error') || err.message.includes('ECONNREFUSED'));
    setError(
      isNetworkError
        ? 'تعذر الاتصال بالخادم.'
        : 'حدث خطأ أثناء المعالجة. يرجى المحاولة مرة أخرى.'
    );
  };

  const buildHistory = (): HistoryItem[] =>
    messagesRef.current.slice(-MAX_HISTORY_MESSAGES).map(({ role, content }) => ({
      role,
      content,
    }));

  const send = useCallback(async (text: string) => {
    if (!text.trim() || isSendingRef.current) return;
    isSendingRef.current = true;

    // بنبني الـ history من الرسايل اللي موجودة *قبل* ما نضيف رسالة المستخدم
    // الحالية، عشان السؤال الحالي يتبعت لوحده في حقل message مش مكرر جوه history
    const history = buildHistory();

    appendMessage(createMessage('user', text));
    setIsLoading(true);
    setError(null);
    try {
      const { answer, images } = await sendMessage(text, history);
      appendMessage(createMessage('assistant', answer, images));
    } catch (err: unknown) {
      handleError(err);
    } finally {
      setIsLoading(false);
      isSendingRef.current = false;
    }
  }, [appendMessage]);

  const sendUserMessage = useCallback((text: string) => send(text), [send]);
  const sendVoiceMessage = useCallback((text: string) => send(text), [send]);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    isLoading,
    isSpeaking,
    error,
    sendUserMessage,
    sendVoiceMessage,
    addAssistantMessage,
    addUserMessage,
    clearError,
  };
}
