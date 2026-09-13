import { BookOpen, Moon, Search, Sun } from 'lucide-react';

/**
 * Top nav shell — brand on the left, a ⌘K search/command trigger in the
 * center, theme toggle on the right. Replaces the old in-sidebar brand row.
 */
export default function TopNav({ isDark, onToggleTheme, onOpenPalette }) {
  return (
    <header className="relative z-40 flex h-16 shrink-0 items-center gap-3 border-b border-glass-border bg-paper/50 px-4 backdrop-blur-xl sm:px-6">
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <div className="bg-bioluminescent flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow-violet">
          <BookOpen className="h-[18px] w-[18px]" aria-hidden="true" />
        </div>
        <div className="leading-tight">
          <p className="font-editorial text-[15px] font-medium tracking-tight text-ink">
            Marginalia
          </p>
          <p className="hidden text-xs text-ink-muted sm:block">
            Notes on your documents
          </p>
        </div>
      </div>

      {/* Command palette trigger */}
      <div className="flex flex-1 justify-center px-2">
        <button
          type="button"
          onClick={onOpenPalette}
          aria-label="Open command palette"
          className="glass group flex w-full max-w-sm items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-ink-muted shadow-subtle transition-all hover:border-brand-300 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <Search className="h-4 w-4 shrink-0 text-ink-faint transition-colors group-hover:text-brand-600" aria-hidden="true" />
          <span className="flex-1 truncate text-left">Search commands…</span>
          <kbd className="rounded-md border border-border bg-paper-200 px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Theme toggle */}
      <button
        type="button"
        onClick={onToggleTheme}
        aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        className="glass flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-ink-muted shadow-subtle transition-all hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      >
        {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
      </button>
    </header>
  );
}