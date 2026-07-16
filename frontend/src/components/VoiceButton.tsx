import { FaMicrophone, FaStop, FaSpinner } from 'react-icons/fa';

interface VoiceButtonProps {
  isRecording: boolean;
  isProcessing: boolean;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
}

/**
 * Microphone button for voice input.
 * Press to start recording, press again to stop.
 * Shows a spinner while the server processes audio.
 */
export function VoiceButton({
  isRecording,
  isProcessing,
  onStart,
  onStop,
  disabled,
}: VoiceButtonProps) {
  const handleClick = () => {
    if (isRecording) onStop();
    else onStart();
  };

  return (
    <button
      onClick={handleClick}
      disabled={disabled || isProcessing}
      title={isRecording ? 'إيقاف التسجيل' : 'تسجيل صوتي'}
      className={`
        w-11 h-11 rounded-full flex items-center justify-center transition-all duration-200 shadow
        ${isRecording
          ? 'bg-red-500 hover:bg-red-600 text-white animate-pulse'
          : isProcessing
          ? 'bg-church-300 text-white cursor-not-allowed'
          : 'bg-church-700 hover:bg-church-600 text-gold-300 hover:text-gold-200'
        }
        disabled:opacity-50
      `}
    >
      {isProcessing ? (
        <FaSpinner className="animate-spin text-sm" />
      ) : isRecording ? (
        <FaStop className="text-sm" />
      ) : (
        <FaMicrophone className="text-sm" />
      )}
    </button>
  );
}
