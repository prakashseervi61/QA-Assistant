import { AlertCircle, RefreshCw } from 'lucide-react';

/**
 * Error banner with a Retry action, for a view whose initial load failed.
 *
 * ponytail: this was duplicated verbatim in Documents and History — same
 * role="alert", same AlertCircle + Retry button. Colour is never the only
 * signal: the alert icon carries the meaning alongside the pink ground.
 */
export function ErrorBanner({ message, onRetry }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded border-[3px] border-nb-line bg-error-bg px-4 py-3"
    >
      <p className="flex items-center gap-2 text-sm font-medium text-ink">
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" strokeWidth={3} />
        <span className="min-w-0 break-words">{message}</span>
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="nb-btn nb-focus !rounded !bg-paper-surface !px-3 !py-1.5 !text-xs !font-bold"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}

export default ErrorBanner;
