// ─ ── Message Types ────────────────────────────────────────────────────────────
export type MessageRole = 'user' | 'assistant';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  images?: string[]; // روابط صور اختيارية مرفقة مع الرد
  audioUrl?: string; // رابط صوت اختياري (زي لحن ترحيب البابا) مرفق مع الرد
}

// ─── API Types ────────────────────────────────────────────────────────────────
// نسخة مبسطة من الرسالة تتبعت للباك إند كـ history — من غير id/timestamp
// اللي مالهاش لازمة في الطلب، وبنفس شكل messages بتاعة Groq (role + content)
export interface HistoryItem {
  role: MessageRole;
  content: string;
}

export interface ChatRequest {
  message: string;
  history?: HistoryItem[];
}

export interface ChatResponse {
  answer: string;
  images?: string[];
  audio_url?: string | null;
}

export interface HealthResponse {
  status: string;
}
