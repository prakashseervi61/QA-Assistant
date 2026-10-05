import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Clock,
  Loader2,
  MessageSquare,
  Search,
  Trash2,
} from 'lucide-react';
import { deleteJSON, fetchJSON } from '../api';
import EmptyState from './EmptyState';
import { ErrorBanner, SkeletonGrid } from './ui';

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
      <SkeletonGrid label="Loading conversation history" />
    );
  }

  if (error && conversations.length === 0) {
    return <ErrorBanner message={error} onRetry={loadHistory} />;
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8 flex flex-wrap items-end gap-4">
        <div>
          <span className="nb-tag">Archive</span>
          <h2 className="mt-4 flex items-center gap-3 text-3xl font-black uppercase text-ink sm:text-4xl">
            History
            <span className="nb-chip tabular-nums !bg-accent-cyan !text-ink-on-accent font-mono text-xs">
              {conversations.length}
            </span>
          </h2>
        </div>

        <div className="relative ml-auto min-w-[14rem] flex-1 sm:max-w-sm">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink"
            aria-hidden="true"
          />
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Filter history"
            aria-label="Filter conversation history"
            className="nb-input nb-focus w-full py-2 pl-9 pr-3"
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

      {filtered.length === 0 ? (
        <div className="nb-card p-6 text-center">
          <p className="text-sm text-ink-secondary">
            No conversations match “{query.trim()}”.
          </p>
        </div>
      ) : (
        <div className="space-y-7">
          {groups.map(group => (
            <section key={group.key} aria-label={group.label}>
              <h3 className="nb-tag mb-4">{group.label}</h3>
              <ul className="nb-bento">
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
                          <div className="nb-card nb-card-dark flex h-full flex-col justify-center gap-3 p-4">
                            <p className="text-sm font-bold uppercase tracking-tight text-paper">
                              Delete this conversation? This cannot be undone.
                            </p>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => remove(conversation.id)}
                                disabled={isDeleting}
                                className="nb-btn nb-focus !rounded !px-3 !py-1.5 !text-xs !font-bold !text-ink-on-accent disabled:opacity-60"
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
                                className="nb-btn nb-focus !rounded !bg-paper !px-3 !py-1.5 !text-xs !font-bold !text-ink hover:!bg-paper-muted"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <motion.button
                            type="button"
                            onClick={() => onOpen?.(conversation.id)}
                            whileHover={{ x: -3, y: -3 }}
                            whileTap={{ x: 2, y: 2 }}
                            transition={{ type: 'spring', stiffness: 320, damping: 22 }}
                            className="nb-card nb-card-hover group flex w-full flex-col p-4 text-left"
                          >
                            <div className="flex items-start justify-between gap-3">
                              {/* Rotate the ground so no two adjacent cards
                                  share a colour. */}
                              <div
                                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded border-[3px] border-nb-line ${
                                  ['bg-pastel-purple', 'bg-pastel-cyan', 'bg-pastel-green', 'bg-pastel-yellow', 'bg-pastel-pink', 'bg-pastel-orange'][index % 6]
                                }`}
                              >
                                <MessageSquare className="h-[18px] w-[18px] text-ink-on-accent" aria-hidden="true" />
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
                                  className="rounded border-2 border-transparent p-1 text-ink-secondary opacity-0 transition hover:border-nb-line hover:text-ink focus-visible:opacity-100 group-hover:opacity-100"
                                >
                                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                                </span>
                                {/* Arrow convention: bold directional arrows,
                                    never chevrons. */}
                                <span
                                  className="mt-0.5 shrink-0 text-xl font-black leading-none text-ink transition-transform group-hover:translate-x-1"
                                  aria-hidden="true"
                                >
                                  →
                                </span>
                              </div>
                            </div>
                            <p className="mt-3 truncate text-sm font-extrabold uppercase tracking-tight text-ink">
                              {title}
                            </p>
                            <p className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[11px] font-bold tabular-nums text-ink-secondary">
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
