import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  ChevronRight,
  Clock,
  History as HistoryIcon,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { deleteJSON, fetchJSON } from '../api';
import EmptyState from './EmptyState';

// ponytail: Intl.RelativeTimeFormat does this natively (incl. locale-aware
// wording) — replaced a hand-rolled min/hour/day cascade.
const RELATIVE = new Intl.RelativeTimeFormat([], { numeric: 'auto' });

/** Format an ISO timestamp as a short, human-friendly relative time. */
function formatRelativeTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 60) return 'Just now';
  if (abs < 3600) return RELATIVE.format(Math.round(seconds / 60), 'minute');
  if (abs < 86400) return RELATIVE.format(Math.round(seconds / 3600), 'hour');
  if (abs < 604800) return RELATIVE.format(Math.round(seconds / 86400), 'day');

  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Group conversations into Today / Yesterday / Earlier for scannability. */
function groupByDay(conversations) {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);

  const groups = [
    { key: 'today', label: 'Today', items: [] },
    { key: 'yesterday', label: 'Yesterday', items: [] },
    { key: 'earlier', label: 'Earlier', items: [] },
  ];

  for (const conversation of conversations) {
    const updated = conversation.updated_at || conversation.created_at;
    const time = updated ? new Date(updated).getTime() : 0;
    if (time >= startOfToday.getTime()) groups[0].items.push(conversation);
    else if (time >= startOfYesterday.getTime()) groups[1].items.push(conversation);
    else groups[2].items.push(conversation);
  }

  return groups.filter(group => group.items.length > 0);
}

/**
 * Saved conversation history.
 *
 * Backed by GET /conversations, which reads from the durable store on disk,
 * so entries outlive a server restart. Supports filtering by title and
 * deleting a single conversation.
 */
export default function HistoryView({ onOpen }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [confirmId, setConfirmId] = useState(null);

  useEffect(() => {
    loadHistory();
    window.addEventListener('conversations-changed', loadHistory);
    return () => window.removeEventListener('conversations-changed', loadHistory);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      // Ask for a generous page so the whole log is visible, not just 10.
      const list = await fetchJSON('/conversations?limit=500');
      setConversations(Array.isArray(list) ? list : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return conversations;
    return conversations.filter(
      c => (c.title || 'New chat').toLowerCase().includes(needle)
    );
  }, [conversations, query]);

  const groups = useMemo(() => groupByDay(filtered), [filtered]);

  async function remove(id) {
    setDeletingId(id);
    try {
      await deleteJSON(`/conversations/${id}`);
      setConversations(prev => prev.filter(c => c.id !== id));
      setConfirmId(null);
    } catch (e) {
      // The shared DELETE helper always parses a JSON body, so a server that
      // replies with an empty body makes a *successful* delete look like a
      // failure. Re-read the list and trust the server's actual state.
      try {
        const list = await fetchJSON('/conversations?limit=500');
        const fresh = Array.isArray(list) ? list : [];
        setConversations(fresh);
        if (!fresh.some(c => c.id === id)) {
          setConfirmId(null);
          return;
        }
        setError(e.message);
      } catch {
        setError(e.message);
      }
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) {
    return (
      <div
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        aria-label="Loading conversation history"
        role="status"
      >
        {[0, 1, 2, 3, 4, 5].map(i => (
          <div key={i} className="glass animate-pulse rounded-2xl p-4">
            <div className="h-10 w-10 rounded-xl bg-paper-300" />
            <div className="mt-3 space-y-2">
              <div className="h-3 w-2/3 rounded bg-paper-300" />
              <div className="h-3 w-1/3 rounded bg-paper-200" />
            </div>
          </div>
        ))}
        <span className="sr-only">Loading conversation history…</span>
      </div>
    );
  }

  if (error && conversations.length === 0) {
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-error-border bg-error-bg px-4 py-3 shadow-subtle"
      >
        <p className="flex items-center gap-2 text-sm text-error-text">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{error}</span>
        </p>
        <button
          type="button"
          onClick={loadHistory}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-error-border bg-paper-100 px-3 py-1.5 text-xs font-medium text-error-text transition-colors hover:bg-error-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h2 className="font-editorial flex items-center gap-2 text-2xl font-medium tracking-tight text-ink">
          <span className="bg-bioluminescent flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow-violet">
            <HistoryIcon className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
          History
        </h2>
        <span className="rounded-full border border-border bg-paper-200 px-2 py-0.5 font-mono text-xs tabular-nums text-ink-secondary">
          {conversations.length}
        </span>

        <div className="relative ml-auto min-w-[14rem] flex-1 sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint"
            aria-hidden="true"
          />
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Filter history…"
            aria-label="Filter conversation history"
            className="w-full rounded-xl border border-border bg-paper-100 py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          />
        </div>
      </div>

      {error && (
        <p role="alert" className="mb-4 text-sm text-error-text">
          {error}
        </p>
      )}

      {conversations.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="No history yet"
          description="Every conversation you start is saved automatically and will show up here, even after a restart."
        />
      ) : null}
      }

      {filtered.length === 0 ? (
        <div className="glass rounded-2xl p-6 text-center shadow-card">
          <p className="text-sm text-ink-secondary">
            No conversations match “{query.trim()}”.
          </p>
        </div>
      ) : (
        <div className="space-y-7">
          {groups.map(group => (
            <section key={group.key} aria-label={group.label}>
              <h3 className="mb-3 font-mono text-xs font-medium uppercase tracking-wider text-ink-faint">
                {group.label}
              </h3>
              <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <AnimatePresence>
                  {group.items.map((conversation, index) => {
                    const title = conversation.title || 'New chat';
                    const count = conversation.message_count ?? 0;
                    const isConfirming = confirmId === conversation.id;
                    const isDeleting = deletingId === conversation.id;
                    return (
                      <motion.li
                        key={conversation.id}
                        layout
                        initial={{ opacity: 0, y: 14 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.96 }}
                        transition={{
                          type: 'spring',
                          stiffness: 300,
                          damping: 26,
                          delay: Math.min(index * 0.03, 0.3),
                        }}
                        className="relative"
                      >
                        {isConfirming ? (
                          <div className="glass flex h-full flex-col justify-center gap-3 rounded-2xl p-4 shadow-card">
                            <p className="text-sm text-ink-secondary">
                              Delete this conversation? This cannot be undone.
                            </p>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => remove(conversation.id)}
                                disabled={isDeleting}
                                className="inline-flex items-center gap-1.5 rounded-lg bg-error-bg px-3 py-1.5 text-xs font-medium text-error-text transition-colors hover:bg-error-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 disabled:opacity-60"
                              >
                                {isDeleting ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                                ) : (
                                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                )}
                                {isDeleting ? 'Deleting…' : 'Delete'}
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmId(null)}
                                disabled={isDeleting}
                                className="inline-flex items-center rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-ink-secondary transition-colors hover:bg-paper-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <motion.button
                            type="button"
                            onClick={() => onOpen?.(conversation.id)}
                            whileHover={{ y: -3 }}
                            whileTap={{ scale: 0.98 }}
                            transition={{ type: 'spring', stiffness: 320, damping: 22 }}
                            className="glass group flex w-full flex-col rounded-2xl p-4 text-left shadow-card transition-colors hover:shadow-card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="bg-bioluminescent flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-glow-violet transition-transform group-hover:scale-105">
                                <MessageSquare className="h-[18px] w-[18px]" aria-hidden="true" />
                              </div>
                              <div className="flex items-center gap-1">
                                <span
                                  role="button"
                                  tabIndex={0}
                                  aria-label={`Delete conversation: ${title}`}
                                  onClick={e => {
                                    e.stopPropagation();
                                    setConfirmId(conversation.id);
                                  }}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      setConfirmId(conversation.id);
                                    }
                                  }}
                                  className="rounded-md p-1 text-ink-faint opacity-0 transition hover:bg-paper-200 hover:text-error-text focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 group-hover:opacity-100"
                                >
                                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                                </span>
                                <ChevronRight
                                  className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint transition-transform group-hover:translate-x-0.5"
                                  aria-hidden="true"
                                />
                              </div>
                            </div>
                            <p className="mt-3 truncate text-sm font-medium text-ink transition-colors group-hover:text-brand-500">
                              {title}
                            </p>
                            <p className="mt-1 flex flex-wrap items-center gap-1.5 font-mono text-xs tabular-nums text-ink-faint">
                              <span>
                                {count > 0
                                  ? `${count} message${count === 1 ? '' : 's'}`
                                  : 'No messages'}
                              </span>
                              {(conversation.updated_at || conversation.created_at) && (
                                <>
                                  <span>·</span>
                                  <span>
                                    {formatRelativeTime(
                                      conversation.updated_at || conversation.created_at
                                    )}
                                  </span>
                                </>
                              )}
                            </p>
                          </motion.button>
                        )}
                      </motion.li>
                    );
                  })}
                </AnimatePresence>
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
