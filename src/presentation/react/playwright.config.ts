import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the smoke suite.
 *
 * Two projects, because the drawer work in this app is the part most likely to
 * regress silently: the desktop rail and the mobile drawer are separate
 * navigation surfaces sharing one URL space, and a change that looks fine at
 * 1440px can leave the phone with no navigation at all. Running the same specs
 * against a real phone profile is the only way that shows up.
 *
 * The suite mocks the API rather than talking to a live backend, so it runs in
 * CI with no Gemini key, no ChromaDB, and no uploaded corpus — and it stays
 * deterministic instead of depending on what an LLM happens to say. See
 * e2e/fixtures.ts for the mocked contract.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL: 'http://127.0.0.1:3100',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'mobile',
      // A real Pixel-ish profile: touch and `hover: none` are what switch the
      // app from the rail to the drawer, so a desktop browser at a small width
      // would not exercise the code path at all.
      use: { ...devices['Pixel 7'] },
    },
  ],

  webServer: {
    // --host 127.0.0.1 is load-bearing: Vite's default binds "localhost", which
    // on Windows resolves to ::1 only, so the readiness probe against 127.0.0.1
    // never sees the server and the run dies on a 60s timeout.
    command: 'npm run dev -- --port 3100 --strictPort --host 127.0.0.1',
    url: 'http://127.0.0.1:3100',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});