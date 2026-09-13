import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  ChevronRight,
  Clock,
  Loader2,
  MessageSquare,
  RefreshCw,
} from 'lucide-react';
import { fetchJSON } from '../api';
import EmptyState from './EmptyState';

/** Format an ISO timestamp as a short, human-friendly relative time. */
function formatRelativeTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin} min ago`;

  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours} hr${diffHours === 1 ? '' : 's'} ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;

  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Recent conversations — fetched from GET /conversations (newest first).
 * Clicking an entry opens that conversation in the chat panel. Rendered as a
 * bento grid of glass tiles so the view stays inside the spatial system.
 */
export default function RecentView({ onOpen }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadRecent();
    window.addEventListener('conversations-changed', loadRecent);
    return () => window.removeEventListener('conversations-changed', loadRecent);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadRecent() {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchJSON('/conversations');
      setConversations(Array.isArray(list) ? list : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function openConversation(id) {
    onOpen?.(id);
  }

  if (loading) {
    return (
      <div
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        aria-label="Loading recent conversations"
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
        <span className="sr-only">Loading recent conversations…</span>
      </div>
    );
  }

  if (error) {
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
          onClick={loadRecent}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-error-border bg-paper-100 px-3 py-1.5 text-xs font-medium text-error-text transition-colors hover:bg-error-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </button>
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div className="mx-auto max-w-6xl">
        <EmptyState
          icon={Clock}
          title="Nothing recent yet"
          description="Documents you open and conversations you have will show up here for quick access."
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex items-center gap-2.5">
        <h2 className="font-editorial flex items-center gap-2 text-2xl font-medium tracking-tight text-ink">
          <span className="bg-bioluminescent flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow-violet">
            <Clock className="h-4.5 w-4.5" aria-hidden="true" />
          </span>
          Recent
        </h2>
        <span className="rounded-full border border-border bg-paper-200 px-2 py-0.5 font-mono text-xs tabular-nums text-ink-secondary">
          {conversations.length}
        </span>
      </div>

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <AnimatePresence>
          {conversations.map((conversation, index) => {
            const title = conversation.title || 'New chat';
            const count = conversation.message_count ?? 0;
            return (
              <motion.li
                key={conversation.id}
                layout
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ type: 'spring', stiffness: 300, damping: 26, delay: Math.min(index * 0.03, 0.3) }}
              >
                <motion.button
                  type="button"
                  onClick={() => openConversation(conversation.id)}
                  whileHover={{ y: -3 }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ type: 'spring', stiffness: 320, damping: 22 }}
                  className="glass group flex w-full flex-col rounded-2xl p-4 text-left shadow-card transition-colors hover:shadow-card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="bg-bioluminescent flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-glow-violet transition-transform group-hover:scale-105">
                      <MessageSquare className="h-4.5 w-4.5" aria-hidden="true" />
                    </div>
                    <ChevronRight
                      className="mt-1.5 h-4 w-4 shrink-0 text-ink-faint transition-transform group-hover:translate-x-0.5"
                      aria-hidden="true"
                    />
                  </div>
                  <p className="mt-3 truncate text-sm font-medium text-ink transition-colors group-hover:text-brand-500">
                    {title}
                  </p>
                  <p className="mt-1 flex items-center gap-1.5 font-mono text-xs tabular-nums text-ink-faint">
                    <span>
                      {count > 0
                        ? `${count} message${count === 1 ? '' : 's'}`
                        : 'No messages'}
                    </span>
                    {conversation.updated_at && (
                      <>
                        <span>·</span>
                        <span>{formatRelativeTime(conversation.updated_at)}</span>
                      </>
                    )}
                  </p>
                </motion.button>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
      <p className="mt-4 font-mono text-xs text-ink-faint">
        Select a conversation to open it in the chat panel.
      </p>
    </div>
  );
}