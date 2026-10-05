import { ShieldAlert } from 'lucide-react';

/**
 * Below this average similarity the answer is unlikely to be well grounded.
 * Shared so the badge and the inline warning can never disagree.
 */
export const LOW_CONFIDENCE_THRESHOLD = 0.45;

/**
 * ConfidenceSignal — how well the cited chunks back an answer.
 *
 * The backend already computes an average similarity score for every answer,
 * but the UI never showed it, so a confidently-worded but weakly-grounded
 * reply looked identical to a well-sourced one. Surfacing it is what lets a
 * reader decide how much to trust what they just read.
 *
 * Renders nothing when no confidence was supplied (e.g. an older message
 * loaded from history, which does not store the score).
 */
export default function ConfidenceSignal({ confidence, className = '' }) {
  if (typeof confidence !== 'number' || Number.isNaN(confidence)) return null;

  const percent = Math.round(Math.min(Math.max(confidence, 0), 1) * 100);
  const isLow = confidence < LOW_CONFIDENCE_THRESHOLD;
  const tone = isLow
    ? 'border-error-border bg-error-bg text-error-text'
    : 'border-border bg-paper-200 text-ink-secondary';
  const label = isLow ? 'Low confidence' : 'Confidence';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] tabular-nums ${tone} ${className}`}
      title={`${label}: ${percent}% average similarity across the cited chunks.`}
    >
      {isLow && <ShieldAlert className="h-3 w-3" aria-hidden="true" />}
      {label} {percent}%
      <span className="sr-only">
        {isLow
          ? ' — the cited chunks matched the question only weakly, so verify this answer against the sources.'
          : ''}
      </span>
    </span>
  );
}