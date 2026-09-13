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
          'Inter',
          'Geist',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        serif: [
          'Inter',
          'Geist',
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
          inverse: 'var(--ink-inverse)',
          line: 'var(--border-default)',
        },
        'dark-sidebar': {
          DEFAULT: 'var(--bg-dark-sidebar)',
          subtle: 'var(--bg-dark-sidebar-subtle)',
          hover: 'var(--bg-dark-sidebar-hover)',
        },
        // Mineral signature palette — Lapis/Burnt Sienna (light) or Verdigris/Soft Ember (dark)
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
        // Mineral accent system (theme-flipped via design tokens)
        bioluminescent: {
          mineral: 'var(--accent-mineral-1)',
          'mineral-deep': 'var(--accent-mineral-3)',
          ember: 'var(--accent-mineral-2)',
        },
        // Semantic status colors (theme-flipped via design tokens)
        success: {
          bg: 'var(--color-success-bg)',
          text: 'var(--color-success-text)',
          border: 'var(--color-success-border)',
          dot: 'var(--color-success-dot)',
        },
        error: {
          bg: 'var(--color-error-bg)',
          text: 'var(--color-error-text)',
          border: 'var(--color-error-border)',
          dot: 'var(--color-error-dot)',
        },
        glass: {
          DEFAULT: 'var(--glass-bg)',
          strong: 'var(--glass-bg-strong)',
          border: 'var(--glass-border)',
        },
      },
      boxShadow: {
        'subtle': 'var(--shadow-subtle)',
        'card': 'var(--shadow-card)',
        'card-hover': 'var(--shadow-hover)',
        'float': 'var(--shadow-float)',
        'glow-violet': 'var(--glow-mineral)',
        'glow-cyan': 'var(--glow-ember)',
        'glow-aurora': 'var(--glow-aurora)',
        'drawer': '-4px 0 24px -2px rgba(28, 25, 23, 0.08)',
        'drawer-left': '4px 0 24px -2px rgba(28, 25, 23, 0.08)',
      },
      backgroundImage: {
        'aurora': 'var(--aurora-mesh)',
        'bioluminescent': 'linear-gradient(135deg, var(--accent-mineral-1) 0%, var(--accent-mineral-2) 100%)',
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