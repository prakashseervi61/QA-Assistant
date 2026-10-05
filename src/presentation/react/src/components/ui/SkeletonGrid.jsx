/**
 * Loading placeholder for the three-up card grids (Documents, History).
 *
 * ponytail: this markup was duplicated verbatim in both views — same
 * `[0..5]` map, same nb-card wrapper, same bar divs. One component, two callers.
 */
export function SkeletonGrid({ label = 'Loading…', count = 6 }) {
  return (
    <div className="nb-bento" aria-label={label} role="status">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="nb-card animate-pulse p-4">
          <div className="h-10 w-10 rounded border-2 border-nb-line bg-paper-muted" />
          <div className="mt-3 space-y-2">
            <div className="h-3 w-2/3 bg-paper-muted" />
            <div className="h-3 w-1/3 bg-paper-subtle" />
          </div>
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export default SkeletonGrid;
