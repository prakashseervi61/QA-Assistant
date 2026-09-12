import { useEffect, useState } from 'react';
import { FiAlertCircle, FiClock, FiLoader, FiMessageSquare, FiRefreshCw } from 'react-icons/fi';
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
 * Clicking an entry opens that conversation in the chat panel.
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
      <div className="space-y-3" aria-label="Loading recent conversations" role="status">
        {[0, 1, 2].map(i => (
          <div key={i} className="flex animate-pulse items-center gap-3 rounded-xl border border-border bg-surface p-3.5 shadow-subtle">
            <div className="h-9 w-9 rounded-lg bg-paper-300" />
            <div className="flex-1 space-y-2">
              <div className="h-3 w-1/3 rounded bg-paper-300" />
              <div className="h-3 w-1/4 rounded bg-paper-200" />
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
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 shadow-subtle"
      >
        <p className="flex items-center gap-2 text-sm text-red-700">
          <FiAlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 break-words">{error}</span>
        </p>
        <button
          type="button"
          onClick={loadRecent}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
        >
          <FiRefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </button>
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <EmptyState
        icon={FiClock}
        title="Nothing recent yet"
        description="Documents you open and conversations you have will show up here for quick access."
      />
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center gap-2.5">
        <h2 className="font-editorial flex items-center gap-2 text-2xl font-medium tracking-tight text-ink">
          <FiClock className="text-brand-600" />
          Recent
        </h2>
        <span className="rounded-full border border-border bg-paper-200 px-2 py-0.5 font-mono text-xs tabular-nums text-ink-secondary">
          {conversations.length}
        </span>
      </div>
      <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-card">
        {conversations.map(conversation => {
          const title = conversation.title || 'New chat';
          return (
            <li key={conversation.id}>
              <button
                type="button"
                onClick={() => openConversation(conversation.id)}
                className="group flex w-full items-center gap-3.5 px-4 py-3.5 text-left transition-colors hover:bg-paper-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-paper-200 text-stone-600 transition-colors group-hover:border-brand-200 group-hover:bg-brand-50 group-hover:text-brand-600">
                  <FiMessageSquare className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink transition-colors group-hover:text-brand-700">
                    {title}
                  </p>
                  <p className="flex items-center gap-1.5 font-mono text-xs tabular-nums text-ink-muted">
                    <span>
                      {conversation.message_count > 0
                        ? `${conversation.message_count} message${conversation.message_count === 1 ? '' : 's'}`
                        : 'No messages'}
                    </span>
                    {conversation.updated_at && (
                      <>
                        <span className="text-ink-muted">·</span>
                        <span>{formatRelativeTime(conversation.updated_at)}</span>
                      </>
                    )}
                  </p>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 font-mono text-xs text-ink-muted">
        Select a conversation to open it in the chat panel.
      </p>
    </div>
  );
}
