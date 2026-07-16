import { FaTimes } from 'react-icons/fa';
import { MdError } from 'react-icons/md';

interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
}

/**
 * Dismissible error notification banner shown below the chat.
 */
export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="mx-4 mb-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 flex items-center justify-between gap-3 animate-fade-in font-arabic text-sm">
      <div className="flex items-center gap-2">
        <MdError className="text-lg flex-shrink-0" />
        <span>{message}</span>
      </div>
      <button
        onClick={onDismiss}
        className="text-red-400 hover:text-red-600 transition-colors flex-shrink-0"
      >
        <FaTimes />
      </button>
    </div>
  );
}
