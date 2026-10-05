/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  // The app's theme lives on `data-theme` (set by src/theme.js and persisted to
  // localStorage), NOT on an OS media query. Without this line Tailwind defaults
  // to `darkMode: 'media'`, so any `dark:` utility added later would follow the
  // user's OS setting and silently disagree with the in-app toggle.
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        // Space Grotesk carries the brutalist geometry (angular, tight);
        // JetBrains Mono stays for labels, metadata and code.
        sans: [
          '"Space Grotesk"',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'sans-serif',
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
        // Every palette entry resolves to a CSS variable from
        // src/styles/design-tokens.css so the whole app inverts when
        // `[data-theme="dark"]` is set on <html>.
        paper: {
          DEFAULT: 'var(--bg-paper)',
          surface: 'var(--bg-surface)',
          subtle: 'var(--bg-subtle)',
          muted: 'var(--bg-muted)',
        },
        ink: {
          DEFAULT: 'var(--ink-primary)',
          primary: 'var(--ink-primary)',
          secondary: 'var(--ink-secondary)',
          muted: 'var(--ink-muted)',
          faint: 'var(--ink-faint)',
          inverse: 'var(--ink-inverse)',
        },
        // The structural colour. Borders and shadows both resolve here, which
        // is what lets the dark theme flip them to paper in one place.
        // `shadow` is the raw colour — the offset shorthands (`--nb-shadow-sm`
        // etc.) are exposed through boxShadow below, because a custom property
        // cannot be both the colour and the shorthand.
        nb: {
          line: 'var(--nb-line)',
          shadow: 'var(--nb-shadow-color)',
          focus: 'var(--nb-focus)',
        },
        // Ink for text sitting ON a vivid accent ground. Deliberately separate
        // from `ink`: the accents are identical in both themes, so the ink on
        // them must be too — using ink-primary here puts paper on yellow in
        // dark theme (1.25:1). `-muted` is for secondary copy on the same
        // grounds; `ink-on-inverse` is for copy on an inverted (.nb-card-dark)
        // ground, which does flip.
        'ink-on-accent': 'var(--ink-on-accent)',
        'ink-on-accent-muted': 'var(--ink-on-accent-muted)',
        'ink-on-inverse-muted': 'var(--ink-on-inverse-muted)',
        'ink-on-purple': 'var(--ink-on-purple)',
        // Flat accent set — rotate 2-3 per surface.
        accent: {
          yellow: 'var(--accent-yellow)',
          magenta: 'var(--accent-magenta)',
          cyan: 'var(--accent-cyan)',
          purple: 'var(--accent-purple)',
          green: 'var(--accent-green)',
          orange: 'var(--accent-orange)',
        },
        pastel: {
          yellow: 'var(--pastel-yellow)',
          cyan: 'var(--pastel-cyan)',
          pink: 'var(--pastel-pink)',
          green: 'var(--pastel-green)',
          purple: 'var(--pastel-purple)',
          orange: 'var(--pastel-orange)',
        },
        // Semantic status
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
        warning: {
          bg: 'var(--color-warning-bg)',
          text: 'var(--color-warning-text)',
        },
      },
      boxShadow: {
        // Hard offsets only — no blur, no spread, no rgba anywhere in this map.
        'brutal-sm': 'var(--nb-shadow-sm)',
        brutal: 'var(--nb-shadow)',
        'brutal-lg': 'var(--nb-shadow-lg)',
        'brutal-none': 'var(--nb-shadow-none)',
      },
      // 4px is the ceiling on structural elements; nothing structural may be
      // rounder than this, so the scale stops here.
      borderRadius: {
        sm: '2px',
        DEFAULT: '4px',
        md: '4px',
        lg: '4px',
        xl: '4px',
        '2xl': '4px',
        '3xl': '4px',
        full: '9999px',
      },
      spacing: {
        // Strict 8pt grid. No odd values.
        xs: '0.5rem',
        sm: '0.75rem',
        md: '1rem',
        lg: '1.5rem',
        xl: '2rem',
      },
    },
  },
  plugins: [],
};
