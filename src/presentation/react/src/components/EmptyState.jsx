import { motion } from 'framer-motion';
import { Archive } from 'lucide-react';

/**
 * Clean, reusable empty state used by views that have no content yet
 * (Collections, Recent, Bookmarks, ...). Purely presentational; renders on
 * the glass surface so it fits the bento/spatial system in both themes.
 *
 * `icon` is any component (lucide icon preferred) — react-icons still work.
 */
export default function EmptyState({ icon: Icon = Archive, title, description, hint }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24 }}
      className="glass flex min-h-[22rem] w-full max-w-lg flex-col items-center justify-center rounded-3xl px-8 py-14 text-center shadow-card"
    >
      <motion.div
        initial={{ scale: 0.85 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 18, delay: 0.05 }}
        className="bg-bioluminescent mb-5 flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-glow-violet"
      >
        <Icon className="h-6 w-6" aria-hidden="true" />
      </motion.div>
      <h2 className="font-editorial text-xl font-medium tracking-tight text-ink">{title}</h2>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-muted">
          {description}
        </p>
      )}
      {hint && (
        <p className="font-mono mt-3 text-xs text-ink-faint">{hint}</p>
      )}
    </motion.div>
  );
}