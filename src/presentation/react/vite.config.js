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