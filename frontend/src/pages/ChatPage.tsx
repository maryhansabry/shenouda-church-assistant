import { useState, useCallback, useEffect } from 'react';
import { GiChurch } from 'react-icons/gi';
import { FaPhone } from 'react-icons/fa';
import { ChatWindow } from '../components/ChatWindow';
import { ChatInput } from '../components/ChatInput';
import { ErrorBanner } from '../components/ErrorBanner';
import { CallModal } from '../components/CallModal';
import { useChat } from '../hooks/useChat';
import { useVoice } from '../hooks/useVoice';
import { useCall } from '../hooks/useCall';

export function ChatPage() {
  const {
    messages,
    isLoading,
    isSpeaking,
    error,
    sendUserMessage,
    addAssistantMessage,
    addUserMessage,
    clearError,
  } = useChat();

  const [callOpen, setCallOpen] = useState(false);

  const handleVoiceAnswer = useCallback(
    async (text: string) => {
      await sendUserMessage(text);
    },
    [sendUserMessage]
  );

  // addUserMessage (مش sendUserMessage) عن قصد: السؤال أصلاً بيتعالج
  // بالكامل عبر WebSocket المكالمة نفسه. استخدام sendUserMessage هنا
  // كان بيبعت طلب /chat مكرر لنفس السؤال (رد مزدوج + توكنز مضاعفة).
  const handleCallTranscript = useCallback(
    (text: string) => { addUserMessage(text); },
    [addUserMessage]
  );

  const handleCallAnswer = useCallback(
    (text: string, images?: string[]) => addAssistantMessage(text, images),
    [addAssistantMessage]
  );

  const { isRecording, isProcessing, startRecording, stopRecording, error: voiceError } =
    useVoice(handleVoiceAnswer);

  const call = useCall({
    onTranscript: handleCallTranscript,
    onAnswer: handleCallAnswer,
  });

  useEffect(() => {
    if (callOpen && call.status === 'idle') {
      call.startCall();
    }
  }, [callOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpenCall = () => setCallOpen(true);
  const handleCloseCall = () => {
    call.endCall();
    setCallOpen(false);
  };

  const combinedError = error || voiceError;

  return (
    <div className="fixed inset-0 flex flex-col overflow-hidden">
{/* الخلفية - صورة الكنيسة، خافتة كديكور، بتتلائم تلقائي مع أي شاشة  className="w-full h-full object-cover opacity-60 object-[50%_center] md:object-center"*/}
<div className="absolute inset-0 -z-10 bg-white">
  <img
    src="/church-bg.jpg"
    alt=""
    className="
w-full
h-full
object-cover
opacity-60
object-[55%_center]
lg:object-center
"
  />
  <div className="absolute inset-0 bg-white/60" />
</div>

      <NavbarWithCall onCallClick={handleOpenCall} isCallActive={call.isCallActive} />

      <div className="flex flex-col flex-1 max-w-4xl mx-auto w-full pt-16 min-h-0 overflow-hidden">
        <ChatWindow messages={messages} isLoading={isLoading} isSpeaking={isSpeaking} />

        {combinedError && (
          <ErrorBanner message={combinedError} onDismiss={clearError} />
        )}

        <ChatInput
          onSend={sendUserMessage}
          onVoiceStart={startRecording}
          onVoiceStop={stopRecording}
          onCallStart={handleOpenCall}
          isLoading={isLoading}
          isRecording={isRecording}
          isVoiceProcessing={isProcessing}
          isCallActive={call.isCallActive}
        />
      </div>

      {callOpen && (
        <CallModal
          onClose={handleCloseCall}
          onTranscript={handleCallTranscript}
          onAnswer={handleCallAnswer}
        />
      )}
    </div>
  );
}

function NavbarWithCall({
  onCallClick,
  isCallActive,
}: {
  onCallClick: () => void;
  isCallActive: boolean;
}) {
  return (
    <nav className="fixed top-0 left-0 right-0 z-40 bg-church-800/95 backdrop-blur-sm border-b border-gold-500/30">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gold-500/20 border border-gold-500/50 flex items-center justify-center">
            <GiChurch className="text-gold-400 text-lg" />
          </div>
          <div className="text-right">
            <h1 className="text-gold-400 font-bold text-lg leading-none font-arabic">شنودة</h1>
            <p className="text-church-300 text-xs font-arabic">مساعد كنيسة الأنبا شنودة</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onCallClick}
            disabled={isCallActive}
            title="مكالمة مباشرة مع شنودة"
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-arabic
              transition-all shadow
              ${isCallActive
                ? 'bg-green-500/30 text-green-300 cursor-default'
                : 'bg-gold-500/20 hover:bg-gold-500/30 text-gold-300 hover:text-gold-200 border border-gold-500/30'
              }
            `}
          >
            <FaPhone className="text-xs" />
            {isCallActive ? 'مكالمة جارية' : 'اتصل بشنودة'}
          </button>
          <div className="text-gold-500/50 text-2xl select-none">✝</div>
        </div>
      </div>
    </nav>
  );
}
