/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#171717',
        background: '#FAFAF8',
        card: '#FFFFFF',
        muted: '#6B7280',
        border: '#E5E7EB',
        hover: '#F3F4F6',
        accent: '#000000',
      },
      spacing: {
        'xs': '0.5rem',
        'sm': '0.75rem',
        'md': '1rem',
        'lg': '1.5rem',
        'xl': '2rem',
      },
    },
  },
  plugins: [],
};