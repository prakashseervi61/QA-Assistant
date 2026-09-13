import { motion } from 'framer-motion';
import { Check, FileSearch, Layers, RefreshCw, Sparkles } from 'lucide-react';

const STAGES = [
  { key: 'rewrite', label: 'Rewriting query', icon: RefreshCw },
  { key: 'retrieve', label: 'Retrieving context', icon: FileSearch },
  { key: 'rerank', label: 'Reranking sources', icon: Layers },
  { key: 'generate', label: 'Generating answer', icon: Sparkles },
];

const STAGE_ORDER = STAGES.map((s) => s.key);

/**
 * PipelineStepper — animated four-stage RAG pipeline indicator shown while
 * an answer is being produced. Completed stages snap to a checkmark, the
 * current stage gets a brand-fill pill, and waiting stages are dimmed.
 */
export default function PipelineStepper({ currentStage = '' }) {
  const currentIndex = STAGE_ORDER.indexOf(currentStage);

  return (
    <div
      className="glass flex items-center gap-1 rounded-full p-1.5"
      role="status"
      aria-live="polite"
    >
      <span className="sr-only">
        {currentStage
          ? `Answering — ${currentStage}`
          : 'Waiting for retrieval pipeline'}
      </span>
      {STAGES.map(({ icon: Icon, label }, index) => {
        const done = currentIndex >= 0 && index < currentIndex;
        const active = index === currentIndex;

        return (
          <motion.div
            key={label}
            animate={{ backgroundColor: active ? 'var(--accent-brand-600)' : 'transparent' }}
            transition={{ type: 'spring', stiffness: 320, damping: 26 }}
            className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium"
            title={label}
          >
            {done ? (
              <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" />
            ) : (
              <Icon
                className={`h-3.5 w-3.5 ${active ? 'animate-pulse' : ''}`}
                aria-hidden="true"
              />
            )}
            <span className={active ? 'text-white' : done ? 'text-ink-secondary' : 'text-ink-faint'}>
              {label}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}