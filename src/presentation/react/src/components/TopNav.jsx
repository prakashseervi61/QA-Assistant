import { BookOpen, Menu, Moon, Search, Sun } from 'lucide-react';

/**
 * Top nav shell — brand on the left, then either the hamburger (below `lg`) or
 * the ⌘K trigger plus the theme toggle (`lg` and up).
 *
 * Neo-Brutalism navbar: white ground, a declared 3px bottom border (no soft
 * fade), brand mark as a bordered accent square, and the search trigger built
 * as a hard-bordered input-like block rather than a floating pill.
 *
 * Mobile carries only the brand and a hamburger. The search trigger needs ~208px
 * of content before it will give any width up, so on a 320px screen it used to
 * shove the theme toggle past the right edge — and because the shell clips
 * overflow rather than scrolling it, the toggle was silently amputated rather
 * than pushed. A phone has no keyboard for ⌘K anyway. Both controls now live in
 * the MobileNav drawer, which has the width to show them properly.
 */
export default function TopNav({ isDark, onToggleTheme, onOpenPalette, drawerOpen, onOpenDrawer }) {
  return (
    <header className="relative z-40 flex h-16 shrink-0 items-center gap-3 border-b-[3px] border-nb-line bg-paper-surface px-4 sm:px-6">
      {/* Brand — bordered yellow square + uppercase wordmark */}
      <div className="flex min-w-0 items-center gap-2.5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-accent-yellow shadow-brutal-sm">
          <BookOpen className="h-[18px] w-[18px] text-ink-on-accent" aria-hidden="true" />
        </div>
        <div className="min-w-0 leading-tight">
          <p className="truncate text-[15px] font-bold uppercase tracking-tight text-ink">
            Marginalia
          </p>
          <p className="nb-label hidden text-[10px] sm:block">Notes on your documents</p>
        </div>
      </div>

      {/* Right-hand controls. ml-auto parks the hamburger against the edge on
          mobile; from `lg` the search trigger takes the slack with flex-1 and
          pushes the theme toggle to the far side. */}
      <div className="ml-auto flex items-center gap-3 lg:flex-1">
        {/* Command palette trigger — hard-bordered, press-down on hover.
            min-w-0 on the wrapper is what lets this give up width rather than
            forcing the header wider than the viewport. */}
        <div className="hidden min-w-0 flex-1 justify-center px-2 lg:flex">
          <button
            type="button"
            onClick={onOpenPalette}
            aria-label="Open command palette"
            className="nb-btn nb-focus group w-full max-w-sm justify-start !rounded !border-[3px] !bg-paper px-3 !py-2 !text-sm !font-medium text-ink-muted"
          >
            <Search className="h-4 w-4 shrink-0 text-ink" aria-hidden="true" />
            <span className="flex-1 truncate text-left">Search commands…</span>
            <kbd className="hidden border-2 border-nb-line bg-paper-surface px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink sm:inline">
              ⌘K
            </kbd>
          </button>
        </div>

        {/* Theme toggle — desktop only; the drawer carries it below `lg`. */}
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          className="nb-icon-btn nb-focus hidden h-10 w-10 shrink-0 lg:inline-flex"
        >
          {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
        </button>

        {/* Hamburger — the mobile navigation trigger. 44px to stay on target
            with a thumb, and aria-expanded so the state is announced. */}
        <button
          type="button"
          onClick={onOpenDrawer}
          aria-label="Open menu"
          aria-expanded={drawerOpen}
          aria-haspopup="dialog"
          className="nb-icon-btn nb-focus h-11 w-11 shrink-0 lg:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
