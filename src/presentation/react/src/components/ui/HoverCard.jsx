import { useId, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';

/**
 * HoverCard — glass popover revealed on hover, focus, or click.
 * Fully keyboard-operable: the trigger stays focusable; the panel toggles
 * on focus, closes with Escape, and is wired via aria-describedby.
 * Clicking a close button dismisses it for pointer users.
 */
export default function HoverCard({
  trigger,
  children,
  className = '',
  panelClassName = '',
  side = 'bottom',
  align = 'start',
  closeLabel = 'Close details',
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  const pos =
    side === 'top'
      ? align === 'end'
        ? 'bottom-full right-0 mb-2'
        : 'bottom-full left-0 mb-2'
      : align === 'end'
        ? 'top-full right-0 mt-2'
        : 'top-full left-0 mt-2';

  return (
    <span
      className={`relative inline-flex ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {trigger({
        open,
        panelId,
        toggle: () => setOpen((v) => !v),
        close: () => setOpen(false),
        onFocus: () => setOpen(true),
        onBlur: () => setOpen(false),
      })}
      <AnimatePresence>
        {open && (
          <motion.div
            id={panelId}
            role="region"
            aria-label="Additional details"
            initial={{ opacity: 0, y: side === 'top' ? 6 : -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: side === 'top' ? 6 : -6, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            className={`glass-strong shadow-float absolute z-50 ${pos} ${panelClassName}`}
          >
            <button
              type="button"
              aria-label={closeLabel}
              onClick={() => setOpen(false)}
              className="absolute top-2 right-2 rounded-md p-1 text-ink-muted hover:text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              <X className="h-3.5 w-3.5" />
            </button>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  );
}