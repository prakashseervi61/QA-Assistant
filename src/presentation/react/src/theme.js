import { safeGetItem, safeSetItem } from './api';

const THEME_KEY = 'marginalia_theme';

/**
 * Theme helpers — the app flips between light and dark by setting
 * `data-theme` on <html>, and the token layer in design-tokens.css
 * swaps the whole palette underneath. Persistence goes through the
 * same fail-silent storage wrappers the API module uses, so private
 * browsing / sandboxed environments still work.
 */

/** Return the stored theme ('light') or the default ('dark' — Kinetic Glass). */
export function getTheme() {
  return safeGetItem(THEME_KEY) === 'light' ? 'light' : 'dark';
}

/** Apply a theme to the document without persisting it. */
export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

/** Apply and persist a theme. */
export function setTheme(theme) {
  applyTheme(theme);
  safeSetItem(THEME_KEY, theme);
}