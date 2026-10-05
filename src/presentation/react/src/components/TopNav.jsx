import { BookOpen, Moon, Search, Sun } from 'lucide-react';

/**
 * Top nav shell — brand on the left, a ⌘K search/command trigger in the
 * center, theme toggle on the right.
 *
 * Neo-Brutalism navbar: white ground, a declared 3px bottom border (no soft
 * fade), brand mark as a bordered accent square, and the search trigger built
 * as a hard-bordered input-like block rather than a floating pill.
 */
export default function TopNav({ isDark, onToggleTheme, onOpenPalette }) {
  return (
    <header className="relative z-40 flex h-16 shrink-0 items-center gap-3 border-b-[3px] border-nb-line bg-paper-surface px-4 sm:px-6">
      {/* Brand — bordered yellow square + uppercase wordmark */}
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded border-[3px] border-nb-line bg-accent-yellow shadow-brutal-sm">
          <BookOpen className="h-[18px] w-[18px] text-ink-on-accent" aria-hidden="true" />
        </div>
        <div className="leading-tight">
          <p className="text-[15px] font-bold uppercase tracking-tight text-ink">
            Marginalia
          </p>
          <p className="nb-label hidden text-[10px] sm:block">Notes on your documents</p>
        </div>
      </div>

      {/* Command palette trigger — hard-bordered, press-down on hover */}
      <div className="flex flex-1 justify-center px-2">
        <button
          type="button"
          onClick={onOpenPalette}
          aria-label="Open command palette"
          className="nb-btn nb-focus group w-full max-w-sm justify-start !rounded !border-[3px] !bg-paper px-3 !py-2 !text-sm !font-medium text-ink-muted"
        >
          <Search className="h-4 w-4 shrink-0 text-ink" aria-hidden="true" />
          <span className="flex-1 truncate text-left">Search commands…</span>
          {/* A ⌘K hint is meaningless without a keyboard, and on mobile this
              control is not the way to navigate — the dock is. */}
          <kbd className="hidden border-2 border-nb-line bg-paper-surface px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink sm:inline">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Theme toggle */}
      <button
        type="button"
        onClick={onToggleTheme}
        aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        className="nb-icon-btn nb-focus h-10 w-10 shrink-0"
      >
        {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
      </button>
    </header>
  );
}
