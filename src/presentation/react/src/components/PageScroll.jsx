import { useEffect, useLayoutEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Saved scroll offsets, keyed by pathname.
 *
 * Keyed on the path rather than the history entry (`location.key`) on purpose:
 * leaving a page and coming back to it pushes a *new* history entry with a new
 * key, so a key-based lookup would always miss and drop the reader at the top.
 */
const scrollPositions = new Map();

/** How long to keep re-applying a saved offset while content settles. */
const RESTORE_WINDOW_MS = 1500;

/**
 * Scrollable page body that remembers where you were.
 *
 * The offset is recorded from a passive `scroll` listener rather than on
 * unmount. React removes a route's DOM during the commit's mutation phase and
 * only then runs passive effect cleanups, so by cleanup time the element is
 * detached and always reads `scrollTop` 0 — reading it in a cleanup silently
 * saves nothing. Listening to `scroll` sidesteps that entirely.
 *
 * Restoration runs in a layout effect (before paint, so nothing visibly jumps)
 * and is re-applied while late-arriving content changes the scrollable height.
 */
export default function PageScroll({ children, className = '' }) {
  const location = useLocation();
  const ref = useRef(null);
  const path = location.pathname;

  // Record the offset as the reader scrolls.
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const onScroll = () => {
      scrollPositions.set(path, el.scrollTop);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [path]);

  // Restore before paint, and keep re-applying while content settles.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;

    const saved = scrollPositions.get(path);
    if (typeof saved !== 'number' || saved <= 0) return undefined;

    const apply = () => {
      if (el.scrollTop !== saved) el.scrollTop = saved;
    };
    apply();

    // A fetched list arrives after mount and grows the scrollable height, which
    // would drop the offset back to the top. Re-apply on every size change
    // until it sticks, then stop.
    let observer;
    if (typeof ResizeObserver !== 'undefined' && el.firstElementChild) {
      observer = new ResizeObserver(() => {
        if (el.scrollTop === saved) {
          observer.disconnect();
          return;
        }
        apply();
      });
      observer.observe(el.firstElementChild);
    }
    const stop = setTimeout(() => observer?.disconnect(), RESTORE_WINDOW_MS);

    return () => {
      observer?.disconnect();
      clearTimeout(stop);
    };
  }, [path]);

  return (
    <div ref={ref} className={`min-h-0 flex-1 overflow-y-auto ${className}`}>
      {children}
    </div>
  );
}
