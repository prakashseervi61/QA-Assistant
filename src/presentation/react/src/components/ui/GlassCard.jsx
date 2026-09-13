import { motion } from 'framer-motion';

/**
 * GlassCard — frosted, theme-flipped surface container with a soft
 * spring entrance. Token-driven (uses the `.glass` utility), so it
 * renders warm-tinted glass in light mode and zinc glass in dark mode.
 */
export default function GlassCard({
  className = '',
  children,
  strong = false,
  entrance = true,
  ...props
}) {
  return (
    <motion.div
      className={`${strong ? 'glass-strong' : 'glass'} rounded-2xl shadow-card ${
        strong ? 'shadow-float' : ''
      } ${className}`}
      {...(entrance
        ? {
            initial: { opacity: 0, y: 10 },
            animate: { opacity: 1, y: 0 },
            transition: { type: 'spring', stiffness: 300, damping: 24 },
          }
        : {})}
      {...props}
    >
      {children}
    </motion.div>
  );
}