import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Moon, Search, Sun, X } from 'lucide-react';
import { NAV_ACCENTS, navItems, newChatAction } from './navItems';

// How long the panel takes to slide out, in ms. Must stay in step with the
// `duration-300` on the transform below: we unmount on a timer, so a shorter
// timer would cut the animation off mid-slide.
const SLIDE_OUT_MS = 300;

/**
 * Mobile navigation drawer — the app's navigation below `lg`.
 *
 * Why a drawer and not the icon-only bottom bar it replaces: a bottom bar caps
 * itself at five unlabelled 44px targets, so every destination has to be reduced
 * to a glyph and the labels disappear. A drawer has room for the name *and* the
 * description of each view, so a first-time visitor can tell History from
 * Documents without already knowing the app. It also gets the two controls the
 * top bar gave up its space for — command search and the theme toggle — so
 * nothing is lost by moving them off the header.
 *
 * Desktop is untouched: from `lg` the Dock rail is the navigation and this
 * whole component stays `display:none`, so there is no JS viewport query to keep
 * in sync with the CSS breakpoint and no state to lose on a rotate.
 *
 * The slide and the scrim are plain CSS transitions on a `translate-x` and an
 * `opacity`, driven by one `shown` flag; the rows stagger in with framer-motion
 * once the panel is mounted. Doing the panel on CSS rather than framer-motion is
 * deliberate — the exit then costs one class flip, there is no exit animation
 * to keep mounted, and `motion-reduce:` can switch the whole thing off.
 *
 * The panel is a real `role="dialog"` with `aria-modal`, so a screen reader
 * treats it as the active surface rather than reading the page behind it.
 */
export default function MobileNav({
  open,
  onClose,
  onNewChat,
  onOpenPalette,
  active,
  freshChat,
  isDark,
  onToggleTheme,
}) {
  const location = useLocation();
  const panelRef = useRef(null);
  const restoreFocusRef = useRef(null);
  const NewChatIcon = newChatAction.icon;

  // Mount while closing so the slide-out can play, then unmount. `rendered`
  // drives existence, `shown` drives the transform.
  const [rendered, setRendered] = useState(open);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (open) {
      setRendered(true);
      // A timer, not requestAnimationFrame: rAF is suspended in a background tab,
      // so a drawer opened from one would mount off-screen and never slide in.
      // The short delay is just to let the off-screen position commit first.
      const timer = setTimeout(() => setShown(true), 20);
      return () => clearTimeout(timer);
    }
    setShown(false);
    const timer = setTimeout(() => setRendered(false), SLIDE_OUT_MS);
    return () => clearTimeout(timer);
  }, [open]);

  // Close on navigation. Tapping a link changes the route without any explicit
  // close call, so without this the drawer would stay open over the new view.
  useEffect(() => {
    onClose();
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // Escape closes, matching the command palette.
  useEffect(() => {
    if (!open) return undefined;
    function handleKeyDown(e) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Move focus into the panel on open and hand it back to the trigger on close,
  // so keyboard and screen-reader users are never stranded behind the overlay.
  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement;
      const timer = setTimeout(() => panelRef.current?.focus(), 20);
      return () => clearTimeout(timer);
    }
    if (restoreFocusRef.current instanceof HTMLElement) {
      restoreFocusRef.current.focus();
      restoreFocusRef.current = null;
    }
    return undefined;
  }, [open]);

  // Stop the page behind from scrolling under the drawer. The shell is already
  // h-screen, but the scroll views inside it are not, and a touch-drag started
  // inside the panel and released outside it would otherwise scroll them.
  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  // Staggered rows: each slides in from the left just after the panel does, so
  // the list reads as arriving rather than appearing all at once.
  const rowVariants = {
    hidden: { opacity: 0, x: -18 },
    visible: i => ({
      opacity: 1,
      x: 0,
      transition: { type: 'spring', stiffness: 340, damping: 30, delay: 0.05 + i * 0.04 },
    }),
  };

  function handleNewChat() {
    onNewChat();
    onClose();
  }

  function handleOpenPalette() {
    onClose();
    onOpenPalette();
  }

  // New chat takes the first accent, then the links follow in order, so adjacent
  // rows still never match — same rule as the desktop rail.
  const idleClass = 'bg-paper-surface text-ink';

  if (!rendered) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      {/* Scrim — tapping it is the "tap outside to dismiss" gesture. */}
      <div
        onClick={onClose}
        aria-hidden="true"
        className={`absolute inset-0 bg-ink/45 transition-opacity duration-200 ease-out motion-reduce:transition-none ${
          shown ? 'opacity-100' : 'opacity-0'
        }`}
      />

      <nav
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Main menu"
        onMouseDown={e => {
          // Only a press that both starts and ends on the panel itself dismisses,
          // so a text selection dragged out of the drawer is not thrown away.
          if (e.target === e.currentTarget) onClose();
        }}
        className={`absolute inset-y-0 left-0 flex w-[min(19rem,86vw)] flex-col border-r-[3px] border-nb-line bg-paper-surface shadow-brutal-lg focus:outline-none transition-transform duration-300 ease-out motion-reduce:transition-none ${
          shown ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Header — brand plus the explicit close, since Escape and the
            backdrop are not discoverable affordances on a touch screen. */}
        <div className="flex items-center justify-between gap-3 border-b-[3px] border-nb-line bg-accent-yellow px-4 py-3.5">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-paper-surface shadow-brutal-sm">
              <BookOpen className="h-[18px] w-[18px] text-ink" aria-hidden="true" />
            </div>
            <span className="truncate text-[15px] font-bold uppercase tracking-tight text-ink-on-accent">
              Marginalia
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="nb-icon-btn nb-focus h-10 w-10 shrink-0"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Scrollable body — a short phone can still overflow this list once the
            search and theme rows are counted. */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4">
          {/* New chat — the primary action, so it gets the full-width plate
              rather than a row in the list. */}
          <motion.button
            type="button"
            custom={0}
            variants={rowVariants}
            initial="hidden"
            animate="visible"
            onClick={handleNewChat}
            aria-current={freshChat === true ? 'page' : undefined}
            className={`mb-2 flex w-full items-center gap-3 rounded border-[3px] border-nb-line px-3 py-3 text-left shadow-brutal-sm transition-transform active:translate-x-[2px] active:translate-y-[2px] active:shadow-none ${
              freshChat
                ? `${NAV_ACCENTS[0].on}`
                : `${idleClass} ${NAV_ACCENTS[0].hover}`
            }`}
          >
            <RowIcon active={freshChat}>
              <NewChatIcon
                className="h-5 w-5"
                aria-hidden="true"
                strokeWidth={freshChat ? 3 : 2}
              />
            </RowIcon>
            <RowText title={newChatAction.name} description={newChatAction.description} />
          </motion.button>

          <div className="my-3 border-t-[3px] border-nb-line" />

          {/* The four views, as labelled rows with their description. */}
          {navItems.map((item, index) => {
            const Icon = item.icon;
            // On a bare `/chat` the New chat plate already reads as selected, so
            // the Chat row stands down instead of lighting up beside it.
            const isActive = active === item.key && !(item.key === 'chat' && freshChat);
            const accent = NAV_ACCENTS[(index + 1) % NAV_ACCENTS.length];
            return (
              <motion.div
                key={item.key}
                custom={index + 1}
                variants={rowVariants}
                initial="hidden"
                animate="visible"
                className="mb-2"
              >
                <Link
                  to={item.path}
                  onClick={onClose}
                  aria-current={isActive ? 'page' : undefined}
                  className={`flex items-center gap-3 rounded border-[3px] border-nb-line px-3 py-3 shadow-brutal-sm transition-transform active:translate-x-[2px] active:translate-y-[2px] active:shadow-none ${
                    isActive ? accent.on : `${idleClass} ${accent.hover}`
                  }`}
                >
                  <RowIcon active={isActive}>
                    <Icon
                      className="h-5 w-5"
                      aria-hidden="true"
                      strokeWidth={isActive ? 3 : 2}
                    />
                  </RowIcon>
                  <RowText title={item.name} description={item.description} />
                </Link>
              </motion.div>
            );
          })}

          <div className="my-3 border-t-[3px] border-nb-line" />

          {/* The two controls the top bar gave up its width for. Keeping them here
              rather than deleting them is the point: a phone has no keyboard, so
              ⌘K is unreachable, and the toggle is the only way out of a
              light-mode install in the sun. */}
          <motion.button
            type="button"
            custom={navItems.length + 1}
            variants={rowVariants}
            initial="hidden"
            animate="visible"
            onClick={handleOpenPalette}
            className="mb-2 flex w-full items-center gap-3 rounded border-[3px] border-nb-line bg-paper-surface px-3 py-3 text-left text-ink shadow-brutal-sm transition-colors hover:bg-paper-subtle active:translate-x-[2px] active:translate-y-[2px] active:shadow-none"
          >
            <RowIcon>
              <Search className="h-5 w-5" aria-hidden="true" />
            </RowIcon>
            <RowText title="Search commands" description="Jump to anything" />
          </motion.button>

          <motion.button
            type="button"
            custom={navItems.length + 2}
            variants={rowVariants}
            initial="hidden"
            animate="visible"
            onClick={onToggleTheme}
            aria-pressed={isDark}
            className="flex w-full items-center gap-3 rounded border-[3px] border-nb-line bg-paper-surface px-3 py-3 text-left text-ink shadow-brutal-sm transition-colors hover:bg-paper-subtle active:translate-x-[2px] active:translate-y-[2px] active:shadow-none"
          >
            <RowIcon>
              {isDark ? (
                <Sun className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Moon className="h-5 w-5" aria-hidden="true" />
              )}
            </RowIcon>
            <RowText
              title={isDark ? 'Light mode' : 'Dark mode'}
              description="Switch appearance"
            />
          </motion.button>
        </div>
      </nav>
    </div>
  );
}

/**
 * The 40px icon chip on the left of every row.
 *
 * A selected row paints its whole plate the accent, so the chip flips to the
 * paper ground to keep the glyph legible and to read as "inset", the same way
 * the desktop rail inverts its selected icon.
 */
function RowIcon({ active = false, children }) {
  return (
    <span
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded border-2 border-nb-line ${
        active ? 'bg-paper-surface text-ink' : 'bg-paper-subtle text-ink'
      }`}
    >
      {children}
    </span>
  );
}

/** Name over description, both truncating so a long string cannot widen the row. */
function RowText({ title, description }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm font-extrabold uppercase tracking-tight">
        {title}
      </span>
      <span className="nb-label mt-0.5 block truncate !text-[10px] opacity-80">
        {description}
      </span>
    </span>
  );
}
