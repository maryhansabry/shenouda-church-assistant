import { useState } from 'react';
import { GiChurch } from 'react-icons/gi';

interface AssistantAvatarProps {
  size?: 'sm' | 'md' | 'lg';
  isSpeaking?: boolean;
  isListening?: boolean;
}

const sizeClasses = {
  sm: 'w-6 h-6 text-sm',
  md: 'w-9 h-9 text-xl',
  lg: 'w-16 h-16 text-3xl',
};

export function AssistantAvatar({
  size = 'sm',
  isSpeaking = false,
  isListening = false,
}: AssistantAvatarProps) {
  const [imgError, setImgError] = useState(false);
  const sizeClass = sizeClasses[size];

  // Animation classes based on state
  const animationClass = isSpeaking
    ? 'scale-110 ring-4 ring-gold-400 ring-offset-2 ring-offset-transparent shadow-gold-300 shadow-lg animate-pulse'
    : isListening
    ? 'scale-105 ring-4 ring-red-400 ring-offset-2 ring-offset-transparent shadow-red-200 shadow-md'
    : 'scale-100 ring-2 ring-gold-500/40';

  const content = !imgError ? (
    <img
      src="/shenoda-robot.png"
      alt="شنودة"
      className={`${sizeClass} rounded-full object-cover w-full h-full`}
      style={{ objectPosition: 'center 50%' }}
      onError={() => setImgError(true)}
    />
  ) : (
    <div
      className={`${sizeClass} rounded-full bg-gradient-to-br from-church-700 to-church-900 flex items-center justify-center`}
    >
      <GiChurch className="text-gold-400" />
    </div>
  );

  return (
    <div
      className={`
        ${sizeClass}
        rounded-full transition-all duration-300 shadow
        ${animationClass}
      `}
    >
      {content}
      {/* Speaking equalizer bars — only on lg size */}
      {isSpeaking && size === 'lg' && (
        <div className="flex items-end justify-center gap-1 mt-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <span
              key={i}
              className="w-1.5 bg-gold-400 rounded-full animate-bounce-dot"
              style={{
                height: `${8 + i * 3}px`,
                animationDelay: `${i * 0.1}s`,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
