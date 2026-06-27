/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        gold: {
          50:  '#fffdf0',
          100: '#fef9c3',
          200: '#fef08a',
          300: '#fde047',
          400: '#facc15',
          500: '#c9a227',  // primary gold
          600: '#a87c1a',
          700: '#85600f',
          800: '#6b4e07',
          900: '#4a3505',
        },
        church: {
          50:  '#f5f0eb',
          100: '#e8ddd0',
          200: '#d4bfa8',
          300: '#bfa082',
          400: '#a07f5a',
          500: '#7a5c35',  // deep wood
          600: '#5e4427',
          700: '#47321c',
          800: '#2e2010',
          900: '#1a1108',
        },
        ivory: '#faf7f2',
        parchment: '#f0ebe0',
      },
      fontFamily: {
        arabic: ['Cairo', 'Noto Naskh Arabic', 'serif'],
      },
      animation: {
        'bounce-dot': 'bounceDot 1.2s infinite ease-in-out',
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.35s ease-out',
      },
      keyframes: {
        bounceDot: {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.3' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
