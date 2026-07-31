import { useEffect, useRef, useState } from 'react';
import { FiChevronDown, FiFileText, FiLoader, FiMessageSquare, FiSend } from 'react-icons/fi';
import { fetchJSON } from '../api';

const SUGGESTIONS = [
  'Summarize the key points of my documents',
  'What are the main topics covered?',
  'How does this relate to the uploaded content?',
];

const MAX_TEXTAREA_HEIGHT = 160; // px

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Best-effort title for a source chunk, falling back to "Source N". */
function getSourceTitle(source, index) {
  const meta = source.metadata || {};
  return meta.filename || meta.source || meta.title || `Source ${index + 1}`;
}

export default function ChatWidget({ conversationId: initialConversationId = null }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(initialConversationId);
  const [expandedSources, setExpandedSources] = useState({});
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Scroll to the newest message when the conversation changes.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  function resetTextareaHeight() {
    const el = textareaRef.current;
    if (el) el.style.height = 'auto';
  }

  function handleInputChange(e) {
    setInput(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function toggleSource(key) {
    setExpandedSources(prev => ({ ...prev, [key]: !prev[key] }));
  }

  async function sendMessage(textOverride) {
    const text = (textOverride ?? input).trim();
    if (!text || loading) return;

    setInput('');
    resetTextareaHeight();

    const userMsg = { role: 'user', content: text, createdAt: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const payload = {
        question: text,
        conversation_id: conversationId,
        top_k: 5,
      };
      const data = await fetchJSON('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (data.conversation_id) setConversationId(data.conversation_id);

      const botMsg = {
        role: 'assistant',
        content: data.answer || data.content || 'No response',
        sources: data.sources || [],
        createdAt: new Date(),
      };
      setMessages(prev => [...prev, botMsg]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Something went wrong: ${err.message}`, error: true, createdAt: new Date() },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-slate-50">
      {/* Messages */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && !loading ? (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-100 text-brand-600">
              <FiMessageSquare className="h-7 w-7" />
            </div>
            <h3 className="mt-4 text-base font-semibold text-slate-900">Ask a question…</h3>
            <p className="mt-1 max-w-xs text-sm text-slate-500">
              Get answers grounded in your uploaded documents.
            </p>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
              {SUGGESTIONS.map(suggestion => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => sendMessage(suggestion)}
                  className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-brand-300 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div role="log" aria-live="polite" className="space-y-4">
            {messages.map((msg, msgIndex) => {
              const isUser = msg.role === 'user';
              return (
                <div key={msgIndex} className={`flex items-end gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
                  {!isUser && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                      <FiMessageSquare className="h-4 w-4" />
                    </div>
                  )}
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
                      isUser
                        ? 'rounded-br-md bg-brand-600 text-white'
                        : msg.error
                          ? 'rounded-bl-md border border-red-200 bg-red-50 text-red-700'
                          : 'rounded-bl-md border border-slate-200 bg-white text-slate-800'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>

                    {!isUser && msg.sources?.length > 0 && (
                      <div className="mt-3 border-t border-slate-100 pt-2.5">
                        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                          Sources
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {msg.sources.map((source, i) => {
                            const key = `${msgIndex}-${i}`;
                            const expanded = Boolean(expandedSources[key]);
                            const score =
                              typeof source.score === 'number' ? Math.round(source.score * 100) : null;
                            return (
                              <button
                                key={key}
                                type="button"
                                onClick={() => toggleSource(key)}
                                aria-expanded={expanded}
                                className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                                  expanded
                                    ? 'border-brand-300 bg-brand-50 text-brand-700'
                                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-brand-300 hover:text-brand-700'
                                }`}
                              >
                                <FiFileText className="h-3 w-3 shrink-0" />
                                <span className="truncate">{getSourceTitle(source, i)}</span>
                                {score != null && (
                                  <span className="shrink-0 text-slate-400">{score}%</span>
                                )}
                                <FiChevronDown
                                  className={`h-3 w-3 shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
                                />
                              </button>
                            );
                          })}
                        </div>

                        {/* Expanded source previews */}
                        <div className="mt-2 space-y-2">
                          {msg.sources.map((source, i) => {
                            const key = `${msgIndex}-${i}`;
                            if (!expandedSources[key]) return null;
                            return (
                              <div
                                key={`${key}-preview`}
                                className="rounded-lg border border-brand-200 bg-brand-50/60 p-3 text-xs text-slate-600"
                              >
                                <p className="mb-1 font-medium text-brand-700">
                                  {getSourceTitle(source, i)}
                                </p>
                                <p className="line-clamp-4 whitespace-pre-wrap">{source.content}</p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    <p
                      className={`mt-1.5 text-[11px] ${isUser ? 'text-brand-100' : msg.error ? 'text-red-400' : 'text-slate-400'}`}
                    >
                      {formatTime(msg.createdAt)}
                    </p>
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="flex items-end gap-2">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                  <FiMessageSquare className="h-4 w-4" />
                </div>
                <div className="rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-1.5">
                    {[0, 1, 2].map(i => (
                      <span
                        key={i}
                        className="h-2 w-2 animate-bounce rounded-full bg-brand-400"
                        style={{ animationDelay: `${i * 150}ms` }}
                      />
                    ))}
                  </div>
                  <span className="sr-only">Assistant is thinking…</span>
                </div>
              </div>
            )}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-slate-200 bg-white p-3">
        <div
          className={`flex items-end gap-2 rounded-xl border bg-white px-3 py-2 transition-colors focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20 ${
            loading ? 'border-slate-200 opacity-60' : 'border-slate-300'
          }`}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents…"
            disabled={loading}
            aria-label="Your question"
            name="question"
            className="max-h-40 min-h-0 flex-1 resize-none bg-transparent py-1 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            aria-label="Send message"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white transition-colors hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading ? (
              <FiLoader className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FiSend className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
        <p className="mt-1.5 text-center text-[11px] text-slate-400">
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}
