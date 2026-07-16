import type { Message } from '../types';
import { AssistantAvatar } from './AssistantAvatar';

interface ChatBubbleProps {
  message: Message;
  isSpeaking?: boolean;
}

export function ChatBubble({ message, isSpeaking = false }: ChatBubbleProps) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-start animate-slide-up">
        <div className="max-w-[80%] bg-gold-500 text-white rounded-2xl rounded-bl-sm px-4 py-3 shadow text-right font-arabic leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-end gap-2 animate-slide-up">
      <AssistantAvatar size="sm" isSpeaking={isSpeaking} />
      <div className={`
        max-w-[80%] bg-white/90 border text-church-800 rounded-2xl rounded-br-sm
        px-4 py-3 shadow-sm text-right font-arabic leading-relaxed transition-all
        ${isSpeaking ? 'border-gold-400 shadow-gold-100 shadow-md' : 'border-church-200'}
      `}>
        {message.content}

        {/* الصور المرفقة مع الرد - بتظهر كصندوق صورة فعلي، مش لينك */}
        {message.images && message.images.length > 0 && (
          <div className={`
            mt-3 grid gap-2
            ${message.images.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}
          `}>
            {message.images.map((src, i) => (
              <img
                key={i}
                src={src}
                alt=""
                loading="lazy"
                className="rounded-lg w-full h-auto object-cover max-h-56 border border-church-200"
                onError={(e) => {
                  // لو الصورة مش موجودة/الرابط عطل، نخفيها بدل ما تبين
                  // أيقونة "صورة مكسورة" في الشات
                  (e.currentTarget as HTMLImageElement).style.display = 'none';
                }}
              />
            ))}
          </div>
        )}

        {/* Speaking indicator */}
        {isSpeaking && (
          <div className="flex gap-1 mt-2 justify-end">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-gold-400 animate-bounce-dot"
                style={{ animationDelay: `${i * 0.2}s` }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
