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
          <div key={i} className="flex animate-pulse items-center gap-3 rounded-xl border border-slate-100 bg-white p-3">
            <div className="h-10 w-10 rounded-lg bg-slate-200" />
            <div className="flex-1 space-y-2">
              <div className="h-3 w-1/3 rounded bg-slate-200" />
              <div className="h-3 w-1/4 rounded bg-slate-200" />
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
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3"
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
      <div className="mb-4 flex items-center gap-2">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <FiClock className="text-brand-600" />
          Recent
        </h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
          {conversations.length}
        </span>
      </div>
      <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
        {conversations.map(conversation => {
          const title = conversation.title || 'New chat';
          return (
            <li key={conversation.id}>
              <button
                type="button"
                onClick={() => openConversation(conversation.id)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <FiMessageSquare className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-800">{title}</p>
                  <p className="text-sm text-slate-500">
                    {conversation.message_count > 0
                      ? `${conversation.message_count} message${conversation.message_count === 1 ? '' : 's'}`
                      : 'No messages'}
                    {conversation.updated_at && ` · ${formatRelativeTime(conversation.updated_at)}`}
                  </p>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-slate-400">
        Select a conversation to open it in the chat panel.
      </p>
    </div>
  );
}
