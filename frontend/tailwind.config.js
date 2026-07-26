/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: '#090a0f',
        darkCard: 'rgba(16, 20, 35, 0.65)',
        darkBorder: 'rgba(255, 255, 255, 0.08)',
        accentGreen: '#10b981',
        accentBlue: '#3b82f6',
        accentCyan: '#06b6d4',
        accentOrange: '#f97316',
        accentRed: '#ef4444'
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif'],
      },
      backdropBlur: {
        xs: '2px',
      }
    },
  },
  plugins: [],
}
