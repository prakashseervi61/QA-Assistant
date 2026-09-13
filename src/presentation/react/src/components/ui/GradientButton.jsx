import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

/**
 * GradientButton — mineral gradient primary action with
 * magnetic hover/tap spring and an optional spinner. Accessible:
 * real <button>, focus ring, disabled handled via aria.
 */
export default function GradientButton({
  children,
  className = '',
  loading = false,
  disabled = false,
  onClick,
  ...props
}) {
  const isDisabled = disabled || loading;
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={isDisabled}
      whileHover={isDisabled ? undefined : { scale: 1.04 }}
      whileTap={isDisabled ? undefined : { scale: 0.96 }}
      transition={{ type: 'spring', stiffness: 400, damping: 22 }}
      aria-busy={loading || undefined}
      className={`bg-bioluminescent relative inline-flex shrink-0 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-white shadow-glow-violet transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {children}
    </motion.button>
  );
}