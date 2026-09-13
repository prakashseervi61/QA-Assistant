/**
 * Best-effort title for a source chunk, falling back to "Source N".
 */
export function getSourceTitle(source, index) {
  const meta = source.metadata || {};
  return meta.filename || meta.source || meta.title || `Source ${index + 1}`;
}