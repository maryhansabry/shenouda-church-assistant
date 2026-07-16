import { GiChurch } from 'react-icons/gi';

/**
 * Top navigation bar with church logo and assistant name.
 */
export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-church-800/95 backdrop-blur-sm border-b border-gold-500/30">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
        {/* Logo + Title */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gold-500/20 border border-gold-500/50 flex items-center justify-center">
            <GiChurch className="text-gold-400 text-lg" />
          </div>
          <div className="text-right">
            <h1 className="text-gold-400 font-bold text-lg leading-none font-arabic">
              شنودة
            </h1>
            <p className="text-church-300 text-xs font-arabic">
              مساعد كنيسة الأنبا شنودة
            </p>
          </div>
        </div>

        {/* Decorative cross */}
        <div className="text-gold-500/50 text-2xl select-none">✝</div>
      </div>
    </nav>
  );
}
