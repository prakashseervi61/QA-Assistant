/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Single accent palette (indigo) used across buttons, active nav
        // items, chat bubbles, links, and empty-state highlights.
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        primary: '#171717',
        background: '#FAFAF8',
        card: '#FFFFFF',
        muted: '#6B7280',
        border: '#E5E7EB',
        hover: '#F3F4F6',
        accent: '#4F46E5',
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