import { motion } from 'framer-motion';
import { ExternalLink, Hash } from 'lucide-react';

/**
 * CitationPill — superscript-style source citation pill in chat answers.
 * Renders the source title + a hovercard with metadata. Safe: `href` is
 * only produced from an allow-listed scheme (https/mailto), never raw.
 */
export default function CitationPill({ index = 0, title = '', source = {} }) {
  const meta = source.metadata || {};
  const page = meta.page;
  const href = safeHref(meta.filename || meta.source || meta.url || '');

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 400, damping: 26, delay: index * 0.03 }}
      className="inline-flex items-center gap-1 text-xs"
      title={title}
    >
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="group inline-flex items-center gap-1 rounded-full border border-strong bg-subtle px-2 py-1 text-ink-secondary hover:border-brand-500 hover:text-brand-500"
        >
          <Hash className="h-3 w-3" aria-hidden="true" />
          {index + 1}
          <ExternalLink
            className="h-3 w-3 opacity-50 transition-opacity group-hover:opacity-100"
            aria-hidden="true"
          />
        </a>
      ) : (
        <span className="inline-flex items-center gap-1 rounded-full border border-strong bg-subtle px-2 py-1 text-ink-secondary">
          <Hash className="h-3 w-3" aria-hidden="true" />
          {index + 1}
        </span>
      )}
      {page != null && (
        <span className="text-[10px] text-ink-faint">p.{page}</span>
      )}
    </motion.span>
  );
}

/** Return href only for allow-listed schemes, else undefined. */
function safeHref(value) {
  if (typeof value !== 'string' || !value) return undefined;
  try {
    const url = new URL(value, window.location.origin);
    if (url.protocol === 'https:' || url.protocol === 'mailto:') return url.toString();
  } catch {
    return undefined;
  }
  return undefined;
}