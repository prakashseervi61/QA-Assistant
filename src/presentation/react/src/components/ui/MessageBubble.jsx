import { motion } from 'framer-motion';
import { AlertCircle, User } from 'lucide-react';
import { getSourceTitle } from '../utils/getSourceTitle';
import CitationPill from './CitationPill';

/**
 * MessageBubble — a single chat message.
 * User messages render as a right-aligned bioluminescent gradient bubble;
 * assistant messages render as a frosted glass panel with shimmer streaming
 * caret and inline source citation pills. Citations are always anchored to
 * a real source; a citation with no backing source never renders a link.
 */
export default function MessageBubble({
  role = 'assistant',
  content = '',
  sources = [],
  isStreaming = false,
  error = false,
  showCitation = true,
}) {
  const isUser = role === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 320, damping: 28 }}
      className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      {isUser ? (
        <div
          className="bg-bioluminescent flex max-w-[85%] items-start gap-3 rounded-2xl rounded-br-md px-4 py-3 text-sm leading-relaxed text-white shadow-glow-violet"
          role="log"
        >
          <User className="mt-0.5 h-4 w-4 shrink-0 opacity-80" aria-hidden="true" />
          <span className="whitespace-pre-wrap break-words">{content}</span>
        </div>
      ) : (
        <div className="glass max-w-[92%] rounded-2xl rounded-bl-md p-4">
          {error && (
            <p className="mb-2 flex items-center gap-2 text-xs font-medium text-error">
              <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
              Something went wrong while answering. Please try again.
            </p>
          )}
          <div className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-ink-primary">
            {content}
            {isStreaming && <span className="caret" aria-label="Streaming" />}
          </div>
          {showCitation && sources.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border-strong pt-2.5">
              <span className="text-xs font-medium tracking-wide text-ink-faint uppercase">
                Sources
              </span>
              {sources.map((source, index) => (
                <CitationPill
                  key={source.id || index}
                  index={index}
                  title={getSourceTitle(source, index)}
                  source={source}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}