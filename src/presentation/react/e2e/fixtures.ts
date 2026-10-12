import { expect, type Page, test } from '@playwright/test';

/**
 * The mocked API contract the smoke suite runs against.
 *
 * Every response here mirrors a real endpoint's shape, so a test that passes
 * against the mock and fails against the live API means the backend changed —
 * which is the whole point. The alternative, pointing CI at a live stack, would
 * need a Gemini key, a populated vector store, and would fail for reasons that
 * have nothing to do with the code under test.
 *
 * SSE is reproduced with a real chunked body rather than a single blob, because
 * a stream that arrives all at once does not exercise the partial-answer
 * rendering path at all.
 */

const DOCUMENTS = [
  {
    document_id: 'doc-1',
    filename: 'applied-cryptography.pdf',
    file_type: '.pdf',
    file_size: 27_008_562,
    chunk_count: 516,
    created_at: '2026-09-30T13:18:43',
  },
];

// A bare list, not `{conversations: [...]}`. ChatWidget reads `data.total` off
// /documents to decide whether to disable the composer, so a mock without that
// key makes every chat test fail on a disabled textarea.
const DOCUMENTS_RESPONSE = { documents: DOCUMENTS, total: DOCUMENTS.length };

const CONVERSATIONS = [
  {
    id: 'conv-1',
    title: 'What is RSA?',
    created_at: '2026-10-05T10:00:00',
    updated_at: '2026-10-05T10:01:00',
    message_count: 2,
  },
];

const USAGE = {
  requests: 3,
  prompt_tokens: 3000,
  completion_tokens: 1210,
  total_tokens: 4210,
  est_cost_usd: 0.0031,
  recent: [],
};

/** Read a streamed body out of a route handler, in SSE frames. */
function sseBody(events: string[]): string {
  return events.map((event) => `data: ${event}\n\n`).join('');
}

/**
 * Install the mock API. Call before the first navigation in every test.
 *
 * `chatAnswer` is overridable so a test can drive a specific streaming state —
 * an error, a refusal, or an empty answer — without a second route table.
 */
export async function mockApi(
  page: Page,
  options: { chatAnswer?: string[]; chatFails?: boolean } = {},
) {
  const chunks = options.chatAnswer ?? [
    'RSA is an ',
    'asymmetric cipher ',
    'used for encryption and signatures.',
  ];

  await page.route('**/api/documents*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DOCUMENTS_RESPONSE),
    }),
  );

  // A bare array, matching what GET /conversations actually returns.
  await page.route('**/api/conversations*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(CONVERSATIONS),
    }),
  );

  await page.route('**/api/settings*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        version: '0.1.0',
        llm_provider: 'gemini',
        llm_model: 'gemini-2.5-flash',
        embedding_model: 'all-MiniLM-L6-v2',
        enable_reranking: true,
        enable_hybrid_search: true,
        enable_semantic_chunking: false,
        enable_guardrails: true,
        max_file_size_mb: 50,
        history_db_path: './data/history.db',
        secrets_file_path: './data/secrets.json',
        history_db_bytes: 4096,
        document_count: DOCUMENTS_RESPONSE.total,
        chunk_count: DOCUMENTS[0].chunk_count,
      }),
    }),
  );

  await page.route('**/api/usage*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(USAGE),
    }),
  );

  await page.route('**/api/health*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' }),
  );

  // The streaming chat endpoint. Registered last so its glob, which is broader
  // than the others, cannot shadow them.
  await page.route('**/api/query/stream', (route) => {
    if (options.chatFails) {
      // The documented failure path is an in-stream error event, not a 500: by
      // the time the model fails the response has already started, so the
      // backend reports it on the stream rather than as a status code.
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: { 'Cache-Control': 'no-cache' },
        body: sseBody([
          JSON.stringify({ type: 'error', message: 'Model unavailable' }),
          '[DONE]',
        ]),
      });
    }
    const events = [
      ...chunks.map((content) => JSON.stringify({ type: 'chunk', content })),
      JSON.stringify({
        type: 'done',
        answer: chunks.join(''),
        // The id the shell adopts into the URL, so a test can assert that a new
        // conversation becomes linkable.
        conversation_id: 'conv-new',
        confidence: 0.82,
        sources: [
          {
            text: 'RSA relies on the difficulty of factoring.',
            metadata: { filename: 'applied-cryptography.pdf', page: 42 },
            score: 0.41,
          },
        ],
      }),
      '[DONE]',
    ];
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'Cache-Control': 'no-cache' },
      body: sseBody(events),
    });
  });
}

/**
 * Navigate by view name, through whichever navigation surface this project uses.
 *
 * Desktop has the icon rail; mobile has the drawer. Selecting on the surface
 * rather than on the URL keeps one spec covering both — and hard-coding one of
 * them would have made the other project's navigation silently untested.
 */
export async function navigateTo(page: Page, view: string) {
  const hamburger = page.getByRole('button', { name: 'Open menu' });
  if (await hamburger.isVisible()) {
    await hamburger.click();
    const drawer = page.getByRole('dialog', { name: 'Main menu' });
    await expect(drawer).toBeVisible();
    // Selected by href, not by accessible name: each drawer's row carries its
    // description too, so the computed name is "Documents Upload and manage…"
    // and a name matcher overlaps its neighbours. The href is also the thing
    // actually worth asserting — a drawer row that navigates somewhere else is
    // the bug this would catch.
    await drawer.locator(`a[href="/${view.toLowerCase()}"]`).click();
    return;
  }
  // exact, and by role: the rail also holds a "New chat" button, so a bare
  // getByLabel('Chat') matches two elements and fails in strict mode.
  await page
    .locator('nav[aria-label="Main navigation"]')
    .getByRole('link', { name: view, exact: true })
    .click();
}

/** Open the navigation. On mobile that is the hamburger drawer. */
export async function openNavigation(page: Page) {
  const hamburger = page.getByRole('button', { name: 'Open menu' });
  if (await hamburger.isVisible()) {
    await hamburger.click();
    await expect(page.getByRole('dialog', { name: 'Main menu' })).toBeVisible();
  }
}

/** Assert the page is free of horizontal overflow — the responsive invariant. */
export async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'page scrolls sideways').toBeLessThanOrEqual(1);
}