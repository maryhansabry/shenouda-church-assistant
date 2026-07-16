// =========================
// Web Speech API type declarations
// (not included in default TS DOM lib)
// مشتركة بين useVoice.ts و useCall.ts عشان نتجنب تكرار الإعلانات
// =========================
export interface SpeechRecognitionResultItem {
  transcript: string;
}
export interface SpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionResultItem;
}
export interface SpeechRecognitionResultList {
  length: number;
  [index: number]: SpeechRecognitionResult;
}
export interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}
export interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}
export interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}
export interface SpeechRecognitionConstructor {
  new (): SpeechRecognition;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}
