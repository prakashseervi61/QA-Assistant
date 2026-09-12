import { FiInbox } from 'react-icons/fi';

/**
 * Clean, reusable empty state used by views that have no content yet
 * (Collections, Recent, Bookmarks, ...). Purely presentational.
 */
export default function EmptyState({ icon: Icon = FiInbox, title, description, hint }) {
  return (
    <div className="mx-auto flex min-h-[22rem] w-full max-w-lg flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-surface px-8 py-14 text-center shadow-subtle">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-paper-200 text-stone-700">
        <Icon className="h-6 w-6 text-stone-600" />
      </div>
      <h2 className="font-editorial text-xl font-medium text-ink">{title}</h2>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-muted">
          {description}
        </p>
      )}
      {hint && (
        <p className="mt-3 font-mono text-xs text-ink-muted">
          {hint}
        </p>
      )}
    </div>
  );
}
