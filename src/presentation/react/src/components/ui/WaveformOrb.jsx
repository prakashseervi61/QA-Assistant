import { motion } from 'framer-motion';
import { Mic, MicOff } from 'lucide-react';

/**
 * WaveformOrb — pulsing voice orb with animated sound bars.
 * `active` drives the bars to animate (listening); `listening` drives the
 * pulse + accent glow and swaps the mic glyph.
 */
export default function WaveformOrb({
  active = false,
  listening = false,
  onClick,
  label = 'Voice input',
  className = '',
}) {
  const bars = 5;
  const activeN = 3; // first N bars active when listening

  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ scale: 1.06 }}
      whileTap={{ scale: 0.94 }}
      transition={{ type: 'spring', stiffness: 400, damping: 22 }}
      aria-label={listening ? 'Stop voice input' : label}
      aria-pressed={listening}
      className={`relative inline-flex h-11 w-11 items-center justify-center rounded-full shadow-glow-violet focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/70 ${
        active ? 'bg-bioluminescent' : 'glass'
      } ${className}`}
    >
      {active && (
        <motion.span
          className="absolute inset-0 rounded-full bg-brand-500/40"
          animate={{ scale: [1, 1.45], opacity: [0.6, 0] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: 'easeOut' }}
          aria-hidden="true"
        />
      )}
      <span className="relative flex h-5 items-center gap-[3px]" aria-hidden="true">
        {Array.from({ length: bars }).map((_, i) => (
          <motion.span
            key={i}
            className={`w-[3px] rounded-full ${i < activeN ? 'bg-white' : 'bg-ink-muted'}`}
            animate={{
              height: active && i < activeN ? [6, 18, 10, 16, 6] : 6,
              backgroundColor: active && i < activeN ? '#ffffff' : 'var(--ink-muted)',
            }}
            transition={
              active
                ? { duration: 1.1, repeat: Infinity, delay: i * 0.12, ease: 'easeInOut' }
                : { duration: 0.2 }
            }
            style={{ height: 6 }}
          />
        ))}
      </span>
      {listening ? (
        <span className="sr-only">Listening</span>
      ) : null}
    </motion.button>
  );
}