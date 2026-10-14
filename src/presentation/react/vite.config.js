import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  // Vitest's default include is `**/*.{test,spec}.*`, which also matches the
  // Playwright specs in e2e/. They import @playwright/test, so running them
  // under Vitest fails on `test.beforeEach` — two runners claiming the same
  // files. Scoping the unit suite to src/ keeps the two from overlapping.
  test: {
    include: ['src/**/*.{test,spec}.{js,jsx}'],
    exclude: ['node_modules/**', 'dist/**', 'e2e/**'],
    coverage: {
      // v8 instruments the running code, so it needs no babel plugin and no
      // source transform — it just reports what actually executed.
      provider: 'v8',
      reporter: ['text', 'html'],
      // Report files that were never loaded, at 0%.
      //
      // Without this the report only lists modules some test happened to
      // import, which is the one failure mode coverage exists to prevent:
      // MobileNav, Dock, TopNav, DocumentList, SettingsPanel, HistoryView and
      // CommandPalette had no tests at all, and an `include` alone did not make
      // them appear — they were simply missing from the table.
      all: true,
      // Distinct from the `include` above, which selects *test files*. This one
      // selects the *subject*: every source file, so untested components show
      // up as 0% instead of being invisible because nothing imported them.
      include: ['src/**/*.{js,jsx}'],
      exclude: [
        'src/main.jsx',
        'src/**/*.test.{js,jsx}',
        'src/__tests__/**',
      ],
      // No `thresholds` yet, for the same reason as the backend: the baseline
      // gets looked at and a number chosen, rather than the other way round.
      // Recorded in docs/TESTING.md.
    },
  },

  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});