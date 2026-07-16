import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import { ChatBubble } from './ChatBubble';
import { TypingIndicator } from './TypingIndicator';
import { AssistantAvatar } from './AssistantAvatar';

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  isSpeaking: boolean;
}

export function ChatWindow({ messages, isLoading, isSpeaking }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const lastAssistantIdx = messages.reduce(
    (last, msg, idx) => (msg.role === 'assistant' ? idx : last),
    -1
  );

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center gap-4 text-center py-8 px-4">
        <AssistantAvatar size="lg" isSpeaking={isSpeaking} />
        <div>
          <h2 className="text-church-800 text-2xl font-bold font-arabic mb-1.5">شنودة</h2>
          <p className="text-church-500 font-arabic text-sm leading-relaxed">
            المساعد الذكي لكنيسة الأنبا شنودة
          </p>
          <p className="text-church-400 font-arabic text-xs mt-2">
            اكتب سؤالك أدناه أو اضغط على الميكروفون للتحدث
          </p>
        </div>
        <div className="flex items-center gap-3 text-gold-400/60 text-sm">
          <span className="w-12 h-px bg-gold-300/50" />✝
          <span className="w-12 h-px bg-gold-300/50" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg, idx) => (
        <ChatBubble
          key={msg.id}
          message={msg}
          isSpeaking={isSpeaking && idx === lastAssistantIdx}
        />
      ))}
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
