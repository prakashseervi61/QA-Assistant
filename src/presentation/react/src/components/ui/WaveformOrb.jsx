import { motion } from 'framer-motion';

/**
 * WaveformOrb — square voice button with animated sound bars.
 * `listening` drives the bars, fills the button with its accent, and is
 * reported through aria-pressed.
 *
 * ponytail: this had an `active` prop as well, but the sole caller passed
 * active={listening} listening={listening} — two names for one signal.
 *
 * Neo-Brutalism: hard border, hard shadow, square corners. The press physics
 * are CSS (translate into its own shadow) rather than a scale spring, because
 * scaling a hard-bordered block looks like a wobble instead of a push.
 */
export default function WaveformOrb({
  listening = false,
  onClick,
  label = 'Voice input',
  className = '',
}) {
  const bars = 5;
  const activeN = 3; // first N bars active when listening

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={listening ? 'Stop voice input' : label}
      aria-pressed={listening}
      className={`relative inline-flex h-11 w-11 shrink-0 items-center justify-center rounded border-[3px] border-nb-line shadow-brutal-sm transition-transform active:translate-x-[3px] active:translate-y-[3px] active:shadow-none ${
        listening ? 'bg-accent-orange text-ink-on-accent' : 'bg-paper-surface text-ink hover:bg-accent-yellow hover:text-ink-on-accent'
      } ${className}`}
    >
      <span className="flex h-5 items-center gap-[3px]" aria-hidden="true">
        {Array.from({ length: bars }).map((_, i) => (
          <motion.span
            key={i}
            className="w-[3px]"
            animate={{
              height: listening && i < activeN ? [6, 18, 10, 16, 6] : 6,
            }}
            transition={
              listening
                ? { duration: 1.1, repeat: Infinity, delay: i * 0.12, ease: 'easeInOut' }
                : { duration: 0.2 }
            }
            style={{
              height: 6,
              backgroundColor:
                listening && i < activeN ? 'var(--ink-primary)' : 'var(--ink-faint)',
            }}
          />
        ))}
      </span>
      {listening ? <span className="sr-only">Listening</span> : null}
    </button>
  );
}
