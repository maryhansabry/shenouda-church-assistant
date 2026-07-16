import { AssistantAvatar } from './AssistantAvatar';

/**
 * Animated "typing" indicator shown while waiting for the API response.
 */
export function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 animate-fade-in">
      <AssistantAvatar size="sm" />
      <div className="bg-white/80 border border-church-200 rounded-2xl rounded-br-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-2 h-2 rounded-full bg-gold-500 animate-bounce-dot"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
