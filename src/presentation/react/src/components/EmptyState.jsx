import { FiInbox } from 'react-icons/fi';

/**
 * Clean, reusable empty state used by views that have no content yet
 * (Collections, Recent, Bookmarks, ...). Purely presentational.
 */
export default function EmptyState({ icon: Icon = FiInbox, title, description, hint }) {
  return (
    <div className="flex min-h-[24rem] w-full flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
        <Icon className="h-7 w-7" />
      </div>
      <h2 className="mt-4 text-base font-semibold text-slate-900">{title}</h2>
      {description && <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-slate-500">{description}</p>}
      {hint && <p className="mt-3 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}
