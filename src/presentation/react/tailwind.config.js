/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"Plus Jakarta Sans"',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        serif: [
          '"Newsreader"',
          'Georgia',
          'Cambria',
          '"Times New Roman"',
          'serif',
        ],
        mono: [
          '"JetBrains Mono"',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
      },
      colors: {
        // All palette entries resolve to CSS variables from
        // src/styles/design-tokens.css so the whole app flips when
        // `[data-theme="dark"]` is set on <html> — component classes stay
        // token-driven (`bg-paper`, `text-ink-muted`, `bg-brand-600`, ...)
        // and the theme swaps underneath them.
        paper: {
          50: 'var(--bg-paper-50)',
          DEFAULT: 'var(--bg-paper)',
          100: 'var(--bg-paper-100)',
          200: 'var(--bg-subtle)',
          300: 'var(--bg-muted)',
          border: 'var(--border-default)',
        },
        ink: {
          DEFAULT: 'var(--ink-primary)',
          primary: 'var(--ink-primary)',
          secondary: 'var(--ink-secondary)',
          muted: 'var(--ink-muted)',
          faint: 'var(--ink-faint)',
          line: 'var(--border-default)',
        },
        // Warm Terracotta / Burnt Amber signature palette (purging generic neon indigo AI slop)
        brand: {
          50: 'var(--accent-brand-50)',
          100: 'var(--accent-brand-100)',
          200: 'var(--accent-brand-200)',
          300: 'var(--accent-brand-300)',
          400: 'var(--accent-brand-400)',
          500: 'var(--accent-brand-500)',
          600: 'var(--accent-brand-600)',
          700: 'var(--accent-brand-700)',
          800: 'var(--accent-brand-800)',
          900: 'var(--accent-brand-900)',
          950: 'var(--accent-brand-950)',
        },
        // Semantic design aliases
        surface: 'var(--bg-surface)',
        primary: 'var(--ink-primary)',
        background: 'var(--bg-paper)',
        card: 'var(--bg-surface)',
        muted: 'var(--ink-muted)',
        border: 'var(--border-default)',
        hover: 'var(--bg-subtle)',
        accent: 'var(--accent-brand-600)',
      },
      boxShadow: {
        'subtle': 'var(--shadow-subtle)',
        'card': 'var(--shadow-card)',
        'card-hover': 'var(--shadow-hover)',
        'float': 'var(--shadow-float)',
        'drawer': '-4px 0 24px -2px rgba(28, 25, 23, 0.08)',
        'drawer-left': '4px 0 24px -2px rgba(28, 25, 23, 0.08)',
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