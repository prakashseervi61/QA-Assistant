import { motion } from 'framer-motion';
import { Archive } from 'lucide-react';

/**
 * Clean, reusable empty state used by views that have no content yet
 * (Collections, Bookmarks, ...). Purely presentational; sits on the
 * hard-bordered surface so it fits the system in both themes.
 *
 * `icon` is any component that accepts the lucide icon props (size, className).
 */
export default function EmptyState({ icon: Icon = Archive, title, description, hint }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24 }}
      className="nb-card flex min-h-[22rem] w-full max-w-lg flex-col items-center justify-center px-8 py-14 text-center"
    >
      <motion.div
        initial={{ scale: 0.85 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 18, delay: 0.05 }}
        className="mb-5 flex h-16 w-16 items-center justify-center rounded border-[3px] border-nb-line bg-accent-orange shadow-brutal-sm"
      >
        <Icon className="h-7 w-7 text-ink-on-accent" aria-hidden="true" />
      </motion.div>
      <h2 className="text-3xl font-black uppercase text-ink">{title}</h2>
      {description && (
        <p className="mt-3 max-w-sm text-base font-medium leading-relaxed text-ink-secondary">
          {description}
        </p>
      )}
      {hint && (
        <p className="nb-label mt-5">{hint}</p>
      )}
    </motion.div>
  );
}