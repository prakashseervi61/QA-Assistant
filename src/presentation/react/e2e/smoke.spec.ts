import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, mockApi, navigateTo } from './fixtures';

/**
 * Smoke suite — the critical paths, not the whole app.
 *
 * Five flows, each of which has broken something before:
 *   1. the app boots and shows a usable empty chat
 *   2. asking a question streams an answer and cites its sources
 *   3. a failed request surfaces an error instead of hanging
 *   4. navigation reaches every view, on whichever surface this project uses
 *   5. the mobile drawer opens, navigates, and closes
 *
 * Navigation is exercised through the helper rather than hard-coded selectors
 * because the two projects have different surfaces: `mobile` must open the
 * drawer first, `desktop` clicks the rail. A spec that hard-coded one would
 * silently skip the other.
 */

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test('boots into a usable empty chat', async ({ page }) => {
  await page.goto('/chat');

  await expect(page.getByRole('heading', { name: /ask a question/i })).toBeVisible();
  await expect(page.getByLabel('Your question')).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Send message' })).toBeVisible();

  // The send button must exist but be inert until there is something to send.
  await expect(page.getByRole('button', { name: 'Send message' })).toBeDisabled();
  await expectNoHorizontalOverflow(page);
});

test('asks a question and streams an answer with sources', async ({ page }) => {
  await page.goto('/chat');

  const box = page.getByLabel('Your question');
  await box.click();
  await box.fill('What is RSA?');
  await page.getByRole('button', { name: 'Send message' }).click();

  // The question stays on screen as part of the transcript.
  await expect(page.getByText('What is RSA?').first()).toBeVisible();

  // The answer arrives chunk by chunk, so assert on the completed text rather
  // than a fragment that may not have streamed yet.
  await expect(page.getByText(/asymmetric cipher used for encryption/i)).toBeVisible();

  // Citations are the point of a RAG answer — an answer with no source chip is
  // a regression, not a cosmetic one.
  await expect(page.getByText(/applied-cryptography\.pdf/i).first()).toBeVisible();
  await expect(page.getByText(/82%/)).toBeVisible();

  // A finished conversation becomes addressable, so the answer can be linked
  // and the back button has somewhere to go.
  await expect(page).toHaveURL(/\/chat\/conv-new/);

  await expectNoHorizontalOverflow(page);
});

test('surfaces a failed request instead of hanging', async ({ page }) => {
  await mockApi(page, { chatFails: true });

  await page.goto('/chat');
  const box = page.getByLabel('Your question');
  await box.click();
  await box.fill('This will fail');
  await page.getByRole('button', { name: 'Send message' }).click();

  // A stream error must reach the user. The composer also has to come back,
  // otherwise the app is stuck in a loading state with no way to retry.
  await expect(page.getByText(/model unavailable/i).first()).toBeVisible();
  await expect(box).toBeEnabled();
});

test('navigates to every view', async ({ page }) => {
  await page.goto('/chat');

  for (const view of ['Documents', 'History', 'Settings', 'Chat'] as const) {
    await navigateTo(page, view);
    await expect(page).toHaveURL(new RegExp(`/${view.toLowerCase()}`));
    await expectNoHorizontalOverflow(page);
  }
});

test('mobile drawer opens, navigates, and closes', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'the drawer only exists below the lg breakpoint');

  await page.goto('/chat');
  const hamburger = page.getByRole('button', { name: 'Open menu' });

  // Closed to begin with, and the toggle reports that state for a screen reader.
  await expect(hamburger).toBeVisible();
  await expect(hamburger).toHaveAttribute('aria-expanded', 'false');

  await hamburger.click();
  const drawer = page.getByRole('dialog', { name: 'Main menu' });
  await expect(drawer).toBeVisible();
  await expect(hamburger).toHaveAttribute('aria-expanded', 'true');

  // The drawer is the only navigation on a phone, so it has to carry the whole
  // app — including the controls the top bar gave up its width for.
  await expect(drawer.getByRole('link')).toHaveCount(4);
  await expect(drawer.getByRole('button', { name: /search commands/i })).toBeVisible();
  await expect(drawer.getByRole('button', { name: /mode/i })).toBeVisible();

  // Escape closes it.
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();

  // Tapping a link navigates and closes it in one gesture.
  await hamburger.click();
  await drawer.locator('a[href="/documents"]').click();
  await expect(page).toHaveURL(/\/documents/);
  await expect(drawer).toBeHidden();

  // And the backdrop closes it without navigating.
  await hamburger.click();
  await expect(drawer).toBeVisible();
  await page.mouse.click(390, 700);
  await expect(drawer).toBeHidden();
});