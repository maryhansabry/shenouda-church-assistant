import { useState, type KeyboardEvent } from 'react';
import { FaPaperPlane, FaPhone } from 'react-icons/fa';
import { VoiceButton } from './VoiceButton';

interface ChatInputProps {
  onSend: (text: string) => void;
  onVoiceStart: () => void;
  onVoiceStop: () => void;
  onCallStart: () => void;
  isLoading: boolean;
  isRecording: boolean;
  isVoiceProcessing: boolean;
  isCallActive: boolean;
}

/**
 * Message input area.
 * Contains: send button, text input, voice recording, real-time call button.
 */
export function ChatInput({
  onSend,
  onVoiceStart,
  onVoiceStop,
  onCallStart,
  isLoading,
  isRecording,
  isVoiceProcessing,
  isCallActive,
}: ChatInputProps) {
  const [text, setText] = useState('');

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isBusy = isLoading || isVoiceProcessing;

  return (
    <div className="border-t border-church-200/60 bg-ivory/80 backdrop-blur-sm px-4 py-3">
      <div className="max-w-4xl mx-auto flex items-end gap-2">
        {/* Send button - يبان أقصى اليمين */}
        <button
          onClick={handleSend}
          disabled={!text.trim() || isBusy || isCallActive}
          title="إرسال"
          className="
            w-11 h-11 rounded-full bg-gold-500 hover:bg-gold-600
            text-white flex items-center justify-center transition-colors
            shadow disabled:opacity-40 disabled:cursor-not-allowed
          "
        >
          <FaPaperPlane className="text-sm" />
        </button>

        {/* Text input */}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="اكتب سؤالك هنا..."
          rows={1}
          disabled={isBusy || isCallActive}
          dir="rtl"
          className="
            flex-1 resize-none rounded-2xl border border-church-300/60
            bg-white/90 px-4 py-2.5 text-church-800 placeholder-church-400
            font-arabic text-sm leading-relaxed focus:outline-none
            focus:ring-2 focus:ring-gold-400/50 focus:border-gold-400
            disabled:opacity-50 transition-all max-h-32 overflow-y-auto
          "
          style={{ minHeight: '44px' }}
        />

        {/* One-shot voice button - يبان شمال */}
        <VoiceButton
          isRecording={isRecording}
          isProcessing={isVoiceProcessing}
          onStart={onVoiceStart}
          onStop={onVoiceStop}
          disabled={isLoading || isCallActive}
        />

        {/* Real-time call button - أقصى الشمال */}
        <button
          onClick={onCallStart}
          disabled={isCallActive || isBusy}
          title="مكالمة مباشرة"
          className={`
            w-11 h-11 rounded-full flex items-center justify-center transition-all shadow
            ${isCallActive
              ? 'bg-green-500 text-white animate-pulse cursor-default'
              : 'bg-church-700 hover:bg-church-600 text-gold-300 hover:text-gold-200'
            }
            disabled:opacity-50
          `}
        >
          <FaPhone className="text-sm" />
        </button>
      </div>

      {/* Hint text */}
      <p className="text-center text-church-400 text-xs font-arabic mt-2">
        {isCallActive
          ? '🔴 مكالمة جارية — اضغط على زر إنهاء المكالمة للخروج'
          : 'Enter للإرسال · Shift+Enter لسطر جديد'}
      </p>
    </div>
  );
}
