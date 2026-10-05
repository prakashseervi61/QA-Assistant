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
    const nav = navItems.filter(item => {
      if (!q) return true;
      const haystack = [item.name, item.description, item.keywords || ''].join(' ').toLowerCase();
      return q.split(/\s+/).every(term => haystack.includes(term));
    });
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
          className="fixed inset-0 z-[60] flex items-start justify-center bg-paper px-4 pt-[12vh]"
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
            className="w-full max-w-lg overflow-hidden rounded border-[3px] border-nb-line bg-paper-surface shadow-brutal-lg"
          >
            {/* Search row */}
            <div className="flex items-center gap-3 border-b-[3px] border-nb-line bg-accent-yellow px-4 py-3.5">
              <Search className="h-4 w-4 shrink-0 text-ink-on-accent" aria-hidden="true" />
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleListKeyDown}
                placeholder="Type a command or search…"
                aria-label="Search commands"
                className="w-full flex-1 bg-transparent text-sm font-bold text-ink-on-accent placeholder:font-medium placeholder:text-ink-on-accent-muted focus:outline-none"
              />
              <kbd className="border-2 border-nb-line bg-paper-surface px-1.5 py-0.5 font-mono text-[10px] font-bold text-ink">
                ESC
              </kbd>
            </div>

            {/* Results */}
            <div
              role="listbox"
              aria-label="Commands"
              className="max-h-72 overflow-y-auto p-3"
            >
              {commands.length === 0 && (
                <p className="px-3 py-6 text-center text-sm font-bold uppercase tracking-wider text-ink-muted">
                  No commands match “{query}”
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
                    className={`flex w-full items-center gap-3 rounded border-[3px] border-nb-line px-3 py-2.5 text-left transition-transform ${
                      active
                        ? 'bg-accent-yellow text-ink-on-accent shadow-brutal-sm'
                        : 'bg-paper-surface text-ink hover:bg-paper-subtle'
                    }`}
                  >
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded border-2 border-nb-line ${
                        active ? 'bg-paper-surface' : 'bg-paper-muted'
                      }`}
                    >
                      <Icon className="h-4 w-4 text-ink" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium leading-tight">
                        {command.kind === 'theme'
                          ? (isDark ? 'Switch to light theme' : 'Switch to dark theme')
                          : command.name}
                      </span>
                      {command.kind === 'nav' && (
                        <span className="nb-label mt-1 block truncate !text-[10px]">
                          {command.description}
                        </span>
                      )}
                    </span>
                    {(command.kind === 'nav' && command.key === active) || command.kind === 'theme' ? (
                      <span className="nb-chip !border-2 !bg-paper-surface !px-2 !py-0.5 font-mono !text-[10px] uppercase">
                        {command.kind === 'theme' ? 'Toggle' : 'Open'}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>

            {/* Footer hints */}
            <div className="flex items-center gap-3 border-t-[3px] border-nb-line bg-paper-subtle px-4 py-2 font-mono text-[10px] font-bold uppercase tracking-wider text-ink-secondary">
              <span className="flex items-center gap-1">
                <kbd className="border-2 border-nb-line bg-paper-surface px-1">↑</kbd>
                <kbd className="border-2 border-nb-line bg-paper-surface px-1">↓</kbd>
                navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="border-2 border-nb-line bg-paper-surface px-1">↵</kbd>
                select
              </span>
              <span className="ml-auto">⌘K</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}