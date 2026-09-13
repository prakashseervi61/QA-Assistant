import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Moon, Search, Sun } from 'lucide-react';
import { navItems } from './navItems';

const THEME_COMMAND = { key: '__theme__', kind: 'theme' };

/**
 * Cmd+K / Ctrl+K command palette — the spatial way to move around the app.
 * - Fuzzy-free: simple case-insensitive substring match over name + description.
 * - Arrow keys move the highlight, Enter runs, Escape closes.
 * - Also exposes the theme toggle so the dark/light flip lives here too.
 */
export default function CommandPalette({ open, onOpen, onClose, active, onNavigate, isDark, onToggleTheme }) {
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  // Global ⌘K / Ctrl+K toggle.
  useEffect(() => {
    function handleKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (open) {
          onClose();
        } else {
          setQuery('');
          setHighlight(0);
          onOpen();
        }
      } else if (open && e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose, onOpen]);

  // Reset + focus the input each time the palette opens.
  useEffect(() => {
    if (open) {
      setQuery('');
      setHighlight(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const commands = useMemo(() => {
    const q = query.trim().toLowerCase();
    const nav = navItems.filter(item =>
      !q ||
      item.name.toLowerCase().includes(q) ||
      item.description.toLowerCase().includes(q)
    );
    const themeMatch = !q || 'theme appearance light dark'.includes(q);
    return [
      ...nav.map(item => ({ ...item, kind: 'nav' })),
      ...(themeMatch ? [THEME_COMMAND] : []),
    ];
  }, [query]);

  useEffect(() => {
    setHighlight(0);
  }, [query]);

  function runCommand(command) {
    if (command.kind === 'theme') {
      onToggleTheme();
    } else {
      onNavigate(command.key);
    }
    onClose();
  }

  function handleListKeyDown(e) {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight(i => (i + 1) % commands.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight(i => (i - 1 + commands.length) % commands.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const selected = commands[highlight];
      if (selected) runCommand(selected);
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 px-4 pt-[12vh] backdrop-blur-sm"
          onMouseDown={e => {
            if (e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ type: 'spring', stiffness: 380, damping: 30 }}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            className="glass-strong w-full max-w-lg overflow-hidden rounded-2xl shadow-float"
          >
            {/* Search row */}
            <div className="flex items-center gap-3 border-b border-border px-4 py-3.5">
              <Search className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleListKeyDown}
                placeholder="Type a command or search…"
                aria-label="Search commands"
                className="w-full flex-1 bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
              />
              <kbd className="rounded-md border border-border bg-paper-200 px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
                esc
              </kbd>
            </div>

            {/* Results */}
            <div
              ref={listRef}
              role="listbox"
              aria-label="Commands"
              className="max-h-72 overflow-y-auto p-2"
            >
              {commands.length === 0 && (
                <p className="px-3 py-6 text-center text-sm text-ink-faint">
                  No commands match “{query}”.
                </p>
              )}
              {commands.map((command, index) => {
                const active = index === highlight;
                const Icon = command.kind === 'theme'
                  ? (isDark ? Sun : Moon)
                  : command.icon;
                return (
                  <button
                    key={command.key}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onMouseEnter={() => setHighlight(index)}
                    onClick={() => runCommand(command)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                      active ? 'bg-bioluminescent text-white shadow-glow-violet' : 'text-ink'
                    }`}
                  >
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                        active
                          ? 'bg-white/15 text-white'
                          : 'bg-paper-200 text-brand-600'
                      }`}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium leading-tight">
                        {command.kind === 'theme'
                          ? (isDark ? 'Switch to light theme' : 'Switch to dark theme')
                          : command.name}
                      </span>
                      {command.kind === 'nav' && (
                        <span className="block truncate text-xs text-ink-faint">
                          {command.description}
                        </span>
                      )}
                    </span>
                    {command.kind === 'nav' && command.key === active && (
                      <span className="text-[10px] uppercase tracking-wider opacity-70">Open</span>
                    )}
                    {command.kind === 'theme' && (
                      <span className="text-[10px] uppercase tracking-wider opacity-70">Toggle</span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Footer hints */}
            <div className="flex items-center gap-3 border-t border-border px-4 py-2 font-mono text-[10px] text-ink-faint">
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-paper-200 px-1">↑</kbd>
                <kbd className="rounded border border-border bg-paper-200 px-1">↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-paper-200 px-1">↵</kbd>
                select
              </span>
              <span className="ml-auto">⌘K to open</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}