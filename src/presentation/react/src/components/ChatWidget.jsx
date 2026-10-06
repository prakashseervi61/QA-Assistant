import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Check, ChevronDown, FileText, Loader2, MessageSquare, Paperclip, Send, ShieldAlert, Sparkles, Square } from 'lucide-react';
import {
  fetchJSON,
  postFormData,
  safeGetItem,
  safeRemoveItem,
  safeSetItem,
  streamChat,
} from '../api';
import Markdown from './Markdown';
import { ConfidenceSignal, WaveformOrb } from './ui';
import { LOW_CONFIDENCE_THRESHOLD } from './ui/ConfidenceSignal';

const SUGGESTIONS = [
  'Summarize the key points of my documents',
  'What are the main topics covered?',
  'How does this relate to the uploaded content?',
];

const ACCEPTED_TYPES = '.pdf,.docx,.txt';

const MAX_TEXTAREA_HEIGHT = 160; // px

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Best-effort title for a source chunk, falling back to "Source N".
 *
 * Exported for testing: this used to live in components/utils/getSourceTitle.js
 * with a character-identical private copy here, so only the test imported the
 * module while the app used the copy.
 */
export function getSourceTitle(source, index) {
  const meta = source.metadata || {};
  return meta.filename || meta.source || meta.title || `Source ${index + 1}`;
}

/** Generates a unique client-side message ID. */
function generateMessageId() {
  return `msg-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

/** Maps a server-side message (snake_case timestamps) to the local message shape. */
function toLocalMessage(m) {
  return {
    id: m.id || generateMessageId(),
    role: m.role,
    content: m.content,
    sources: m.sources || [],
    createdAt: new Date(m.created_at),
  };
}

export default function ChatWidget() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  // The conversation currently displayed. Mirrors the `:id` route segment —
  // null on `/chat` (fresh) and the conversation uuid on `/chat/<id>`.
  const [conversationId, setConversationId] = useState(null);
  const [expandedSources, setExpandedSources] = useState({});
  const [hasDocuments, setHasDocuments] = useState(null); // null = still checking
  const [restoring, setRestoring] = useState(false); // gates empty-state flash
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const [stages, setStages] = useState([]); // live RAG pipeline trace from `stage` stream events
  const [showJumpToLatest, setShowJumpToLatest] = useState(false); // scrolled-up affordance
  const navigate = useNavigate();
  const { conversationId: routeConversationId } = useParams();
  const messagesContainerRef = useRef(null);
  const stickToBottomRef = useRef(true); // auto-follow only while the user stays at the bottom
  const textareaRef = useRef(null);
  const chatFileInputRef = useRef(null); // hidden input for in-chat uploads
  const recognitionRef = useRef(null); // SpeechRecognition instance
  const abortRef = useRef(null); // AbortController for the in-flight stream
  const isSendingRef = useRef(false); // Execution lock preventing rapid double-send
  const pendingTextRef = useRef(''); // buffered stream text not yet flushed to state
  const flushRafRef = useRef(0); // requestAnimationFrame id for the pending flush
  const pendingIdRef = useRef(null); // message id the buffered text belongs to
  const shownIdRef = useRef(null); // conversation id whose messages are in state
  const loadSeqRef = useRef(0); // invalidates superseded conversation loads

  // Check whether any documents are available to query.
  useEffect(() => {
    let cancelled = false;
    function checkDocuments() {
      fetchJSON('/documents')
        .then(data => {
          if (!cancelled) setHasDocuments((data.total ?? 0) > 0);
        })
        .catch(() => {
          // Never lock the chat out just because the check failed.
          if (!cancelled) setHasDocuments(true);
        });
    }
    checkDocuments();
    window.addEventListener('documents-changed', checkDocuments);
    return () => {
      cancelled = true;
      window.removeEventListener('documents-changed', checkDocuments);
    };
  }, []);

  // The URL is the single source of truth for which conversation is shown:
  // `/chat` is a fresh chat and `/chat/<id>` opens that conversation. Because
  // react-router keeps this component mounted when only the param changes, we
  // watch the param and load/reset on every change.
  useEffect(() => {
    // Bumping the sequence invalidates any in-flight load, so a slow response
    // can never overwrite the conversation the user has since navigated to.
    const seq = ++loadSeqRef.current;
    const isStale = () => seq !== loadSeqRef.current;
    const id = routeConversationId;

    if (!id) {
      shownIdRef.current = null;
      setMessages([]);
      setConversationId(null);
      setExpandedSources({});
      stickToBottomRef.current = true;
      setShowJumpToLatest(false);
      setRestoring(false);
      return;
    }

    // The first message adopts the id from the stream, and that exchange is
    // already rendered locally — refetching it would be a pointless round trip.
    if (id === shownIdRef.current) {
      setRestoring(false);
      return;
    }

    setRestoring(true);
    stickToBottomRef.current = true;
    setShowJumpToLatest(false);
    fetchJSON(`/conversations/${id}`)
      .then(msgs => {
        if (isStale()) return;
        shownIdRef.current = id;
        setMessages(msgs.map(toLocalMessage));
        setConversationId(id);
        setExpandedSources({});
      })
      .catch(() => {
        // Unknown id: fall back to a fresh chat so the URL never lies.
        if (isStale()) return;
        shownIdRef.current = null;
        navigate('/chat', { replace: true });
      })
      .finally(() => {
        if (!isStale()) setRestoring(false);
      });
  }, [routeConversationId, navigate]);

  // Auto-scroll with the stream, but only while the user is near the bottom;
  // scrolling up stops the chasing so partial answers can be read.
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (container && stickToBottomRef.current) container.scrollTop = container.scrollHeight;
  }, [messages, loading]);

  // Abort any in-flight stream if the widget unmounts (e.g. mobile drawer close).
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      resetPendingText();
    };
  }, []);

  // Stop any in-flight speech recognition if the widget unmounts.
  useEffect(() => {
    return () => recognitionRef.current?.stop();
  }, []);

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
    // Enter submits, unless Shift (newline) or an IME composition is active
    // (composing languages like CJK would otherwise send mid-conversion).
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      sendMessage();
    }
  }

  function toggleSource(key) {
    setExpandedSources(prev => ({ ...prev, [key]: !prev[key] }));
  }

  /** Track whether the user is anchored to the newest message (within 120px of bottom). */
  function handleMessagesScroll(e) {
    const container = e.currentTarget;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
    stickToBottomRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom);
  }

  /** Jump to the newest message and resume auto-following. */
  function jumpToLatest() {
    stickToBottomRef.current = true;
    const container = messagesContainerRef.current;
    if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    setShowJumpToLatest(false);
  }

  /**
   * Tell the History view its list is stale.
   *
   * ponytail: the chat no longer renders the conversation list itself (the
   * picker is gone), so it just pings HistoryView to re-fetch.
   */
  function notifyConversationsChanged() {
    window.dispatchEvent(new CustomEvent('conversations-changed'));
  }

  /** Immutably patch the message with the given `id` in the message list. */
  function updateMessageById(id, updater) {
    setMessages(prev => prev.map(msg => (msg.id === id ? updater(msg) : msg)));
  }

  /** Commit whatever stream text is buffered, then clear the buffer. */
  function flushPendingText() {
    if (flushRafRef.current) {
      cancelAnimationFrame(flushRafRef.current);
      flushRafRef.current = 0;
    }
    const id = pendingIdRef.current;
    const text = pendingTextRef.current;
    pendingTextRef.current = '';
    pendingIdRef.current = null;
    if (id && text) {
      updateMessageById(id, msg => ({ ...msg, content: msg.content + text }));
    }
  }

  /**
   * Append streamed text to the assistant message with `id`.
   *
   * The provider streams many small chunks per second; committing each one
   * to state would re-render the whole message list that often. Buffer the
   * text and flush it once per animation frame instead — the rendered
   * result is identical, but the commit rate is capped at the display rate.
   */
  function appendStreamText(id, text) {
    // No requestAnimationFrame (non-DOM context): commit immediately.
    if (typeof requestAnimationFrame !== 'function') {
      updateMessageById(id, msg => ({ ...msg, content: msg.content + text }));
      return;
    }
    pendingIdRef.current = id;
    pendingTextRef.current += text;
    if (!flushRafRef.current) {
      flushRafRef.current = requestAnimationFrame(flushPendingText);
    }
  }

  /** Drop any buffered text without committing it (e.g. on abort/teardown). */
  function resetPendingText() {
    if (flushRafRef.current && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(flushRafRef.current);
      flushRafRef.current = 0;
    }
    pendingTextRef.current = '';
    pendingIdRef.current = null;
  }

  /** Flag the assistant message with `id` as failed, preserving partial content. */
  function markStreamError(id, message) {
    updateMessageById(id, msg => {
      const note = `Something went wrong: ${message}`;
      return {
        ...msg,
        error: true,
        content: msg.content ? `${msg.content}\n\n${note}` : note,
      };
    });
  }

  /** Stop the in-flight stream; the partial answer stays on screen. */
  function stopStreaming() {
    abortRef.current?.abort();
  }

  /** Upload a document picked from the chat composer. */
  async function handleChatUpload(e) {
    const selected = e.target.files?.[0];
    if (!selected || uploading) return;
    setUploading(true);
    setUploadError(null);
    const formData = new FormData();
    formData.append('file', selected);
    try {
      await postFormData('/documents/upload', formData);
      setHasDocuments(true);
      window.dispatchEvent(new CustomEvent('documents-changed'));
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      if (chatFileInputRef.current) chatFileInputRef.current.value = '';
    }
  }

  /** Toggle voice-to-text dictation into the composer. */
  function toggleVoice() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setVoiceError('Voice input is not supported in this browser');
      return;
    }
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    setVoiceError(null);
    const recognition = new Recognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;

    let finalTranscript = '';

    recognition.onstart = () => {
      setListening(true);
      textareaRef.current?.focus();
    };

    recognition.onresult = event => {
      let interimTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i][0];
        if (event.results[i].isFinal) finalTranscript += result.transcript;
        else interimTranscript += result.transcript;
      }
      setInput(finalTranscript + interimTranscript);
      const el = textareaRef.current;
      if (el) {
        el.style.height = 'auto';
        el.style.height = `${el.scrollHeight}px`;
      }
    };

    recognition.onend = () => setListening(false);

    recognition.onerror = event => {
      setListening(false);
      if (event.error && event.error !== 'aborted' && event.error !== 'no-speech') {
        setVoiceError(
          event.error === 'not-allowed'
            ? 'Microphone access was denied — allow the microphone and try again'
            : `Voice input error: ${event.error}`
        );
      }
    };

    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }

  async function sendMessage(textOverride) {
    const text = (textOverride ?? input).trim();
    if (!text || loading || hasDocuments === false || restoring || isSendingRef.current) return;
    isSendingRef.current = true;
    stickToBottomRef.current = true;
    setShowJumpToLatest(false);

    setInput('');
    resetTextareaHeight();
    setStages([]);

    const userMsg = {
      id: generateMessageId(),
      role: 'user',
      content: text,
      createdAt: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    // Append the assistant bubble once; streamed chunks fill it in incrementally.
    const botId = generateMessageId();
    const botMsg = {
      id: botId,
      role: 'assistant',
      content: '',
      sources: [],
      createdAt: new Date(),
    };
    setMessages(prev => [...prev, botMsg]);

    const controller = new AbortController();
    abortRef.current = controller;

    let streamError = null;
    let doneEvent = null;
    let blockedEvent = null;

    try {
      const payload = {
        question: text,
        conversation_id: conversationId,
        top_k: 5,
      };
      await streamChat(payload, {
        signal: controller.signal,
        onEvent(event) {
          switch (event.type) {
            case 'chunk':
              appendStreamText(botId, event.content ?? '');
              break;
            case 'done':
              // The last chunks may still be buffered; commit them before
              // attaching sources so the bubble shows the full answer.
              flushPendingText();
              doneEvent = event;
              if (event.conversation_id) {
                // The first message mints the conversation. Adopt the id into
                // state *and* the URL so the address bar owns it from here on.
                // `replace` keeps Back pointing at wherever the user came
                // from instead of at this just-created empty chat.
                shownIdRef.current = event.conversation_id;
                setConversationId(event.conversation_id);
                if (routeConversationId !== event.conversation_id) {
                  navigate(`/chat/${event.conversation_id}`, { replace: true });
                }
                notifyConversationsChanged();
              }
              // Keep the confidence the backend computed so the answer can
              // show how strongly it is grounded instead of looking equally
              // trustworthy no matter how weak the citations were.
              if (typeof event.confidence === 'number') {
                updateMessageById(botId, msg => ({
                  ...msg,
                  confidence: event.confidence,
                }));
              }
              if (event.sources?.length > 0) {
                updateMessageById(botId, msg => ({ ...msg, sources: event.sources }));
              }
              break;
            case 'error':
              streamError = event.message || 'Stream failed';
              break;
            case 'blocked':
              // Input guardrails blocked the question: record the server's
              // message and close the stream (the abort rejects the in-flight
              // read below). Nothing is persisted or refreshed here.
              blockedEvent = event;
              controller.abort();
              break;
            case 'stage':
              // Live retrieval-trace event, e.g. "rewriting", "retrieving",
              // "reranking", "generating". Append so the assistant bubble can
              // show which pipeline step is running before text arrives.
              setStages(prev => [...prev, { stage: event.stage, detail: event.detail }]);
              break;
            default:
              break;
          }
        },
      });

      if (streamError) {
        markStreamError(botId, streamError);
      } else if (controller.signal.aborted) {
        // User pressed stop — keep the partial answer as-is.
      } else if (doneEvent) {
        // Stream completed cleanly; never leave a visually empty bubble.
        updateMessageById(botId, msg => (msg.content ? msg : { ...msg, content: 'No response' }));
      } else {
        markStreamError(botId, 'Stream ended before a complete response');
      }
    } catch (err) {
      if (blockedEvent) {
        markStreamError(botId, blockedEvent.message || 'Your question was blocked');
      } else if (!controller.signal.aborted) {
        markStreamError(botId, err.message || 'Unknown error');
      }
    } finally {
      // Commit any last buffered text (clean finish or error), then clear
      // the buffer so a stale frame can never write into a new message.
      flushPendingText();
      abortRef.current = null;
      setLoading(false);
      setStages([]);
      isSendingRef.current = false;
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-paper">


      {/* Messages */}
      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        className="relative min-h-0 flex-1 overflow-y-auto"
      >
        {messages.length === 0 && restoring ? (
          <div className="flex h-full flex-col items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-ink" aria-hidden="true" />
            <span className="sr-only">Loading conversation…</span>
          </div>
        ) : messages.length === 0 && !loading ? (
          hasDocuments === false ? (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded border-[3px] border-nb-line bg-accent-yellow shadow-brutal">
                <Paperclip className="h-7 w-7 text-ink-on-accent" aria-hidden="true" />
              </div>
              <h3 className="text-2xl font-black uppercase text-ink">
                Upload a document to continue
              </h3>
              <p className="mt-1 max-w-xs text-sm leading-relaxed text-ink-muted">
                No documents are available yet. Upload a PDF, DOCX or TXT using the
                button below, or from the Documents view.
              </p>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded border-[3px] border-nb-line bg-accent-cyan shadow-brutal">
                <MessageSquare className="h-7 w-7 text-ink-on-accent" aria-hidden="true" />
              </div>
              <h3 className="text-2xl font-black uppercase text-ink">Ask a question</h3>
              <p className="mt-1 max-w-xs text-sm leading-relaxed text-ink-muted">
                Get answers grounded in your uploaded documents.
              </p>
              {hasDocuments === true && (
                <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
                  {SUGGESTIONS.map(suggestion => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => sendMessage(suggestion)}
                      className="nb-btn nb-focus !justify-start !gap-0 !rounded !bg-paper-surface !px-3.5 !py-1.5 !text-xs !font-bold hover:!bg-accent-yellow hover:!text-ink-on-accent"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        ) : (
          <div role="log" aria-live="polite" className="mx-auto w-full max-w-4xl space-y-5 px-4 py-6 pb-24 sm:px-8 lg:pb-6">
            {messages.map((msg, msgIndex) => {
              const isUser = msg.role === 'user';
              const showInlineSources = !isUser && msg.sources?.length > 0 && !loading;
              const isLowConfidence =
                !isUser &&
                typeof msg.confidence === 'number' &&
                msg.confidence < LOW_CONFIDENCE_THRESHOLD;
              return (
                <div key={msg.id} className={`flex items-start gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
                  {!isUser && (
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-accent-magenta">
                      <Sparkles className="h-4 w-4 text-ink-on-accent" aria-hidden="true" />
                    </div>
                  )}
                  <div
                    className={`${
                      isUser
                        ? 'max-w-[85%] rounded border-[3px] border-nb-line bg-accent-yellow px-4 py-3 text-sm font-medium leading-relaxed text-ink-on-accent shadow-brutal'
                        : msg.error
                          ? 'max-w-[88%] rounded border-[3px] border-nb-line bg-error-bg px-4 py-3.5 text-sm font-medium leading-relaxed text-ink-on-accent shadow-brutal'
                          : 'max-w-[88%] rounded border-[3px] border-nb-line bg-paper-surface px-4 py-3.5 text-sm font-medium leading-relaxed text-ink shadow-brutal'
                    }`}
                  >
                    {!isUser && msg.content === '' && loading ? (
                      stages.length > 0 ? (
                        <div className="space-y-1.5 py-1">
                          {stages.map((s, i) => {
                            const isActive = i === stages.length - 1;
                            return (
                              <div key={`${msg.id}-${s.stage}-${i}`} className="flex items-center gap-2 text-xs">
                                {isActive ? (
                                  <Loader2
                                    className="h-3.5 w-3.5 shrink-0 animate-spin text-ink"
                                    aria-hidden="true"
                                  />
                                ) : (
                                  <Check
                                    className="h-3.5 w-3.5 shrink-0 text-ink"
                                    aria-hidden="true"
                                    strokeWidth={3}
                                  />
                                )}
                                <span
                                  className={
                                    isActive
                                      ? 'font-bold uppercase tracking-wider text-ink'
                                      : 'font-bold uppercase tracking-wider text-ink-muted'
                                  }
                                >
                                  {s.detail}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 py-1">
                          {[0, 1, 2].map(i => (
                            <span
                              key={i}
                              className="h-2.5 w-2.5 animate-bounce bg-accent-magenta"
                              style={{ animationDelay: `${i * 150}ms` }}
                            />
                          ))}
                          <span className="sr-only">Assistant is thinking…</span>
                        </div>
                      )
                    ) : (
                      msg.error ? (
                        <p className="whitespace-pre-wrap">{msg.content}</p>
                      ) : msg.content ? (
                        <>
                          {isLowConfidence && (
                            <p className="nb-chip mb-2.5 items-start !rounded !border-[3px] !bg-error-bg !px-2.5 !py-1.5 !text-xs">
                              <ShieldAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" strokeWidth={3} />
                              <span>
                                The cited passages only weakly match your
                                question — check the sources before relying on
                                this answer.
                              </span>
                            </p>
                          )}
                          <Markdown content={msg.content} />
                          {!isUser && loading && <span className="caret" aria-hidden="true" />}
                        </>
                      ) : null
                    )}

                    {!isUser && !loading && typeof msg.confidence === 'number' && !msg.error && (
                      <div className="mt-3 flex justify-end border-t-[3px] border-nb-line pt-2">
                        <ConfidenceSignal confidence={msg.confidence} />
                      </div>
                    )}

                    {showInlineSources && (
                      <div className="mt-3 border-t-[3px] border-nb-line pt-3">
                        <p className="nb-label mb-2">Referenced Sources</p>
                        <div className="flex flex-wrap gap-1.5">
                          {msg.sources.map((source, i) => {
                            const key = `${msg.id}-${i}`;
                            const expanded = Boolean(expandedSources[key]);
                            const score =
                              typeof source.score === 'number' ? Math.round(source.score * 100) : null;
                            return (
                              <button
                                key={key}
                                type="button"
                                onClick={() => toggleSource(key)}
                                aria-expanded={expanded}
                                className={`inline-flex max-w-full items-center gap-1.5 rounded border-2 border-nb-line px-2.5 py-1 font-mono text-[11px] font-bold transition-colors ${
                                  expanded
                                    ? ' text-ink-on-accent'
                                    : 'bg-paper-surface text-ink-secondary hover:bg-accent-yellow hover:text-ink-on-accent'
                                }`}
                              >
                                <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
                                <span className="truncate">{getSourceTitle(source, i)}</span>
                                {score != null && (
                                  <span className="shrink-0 tabular-nums text-ink">
                                    {score}%
                                  </span>
                                )}
                                <ChevronDown
                                  className={`h-3 w-3 shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
                                  aria-hidden="true"
                                />
                              </button>
                            );
                          })}
                        </div>

                        {/* Expanded source previews */}
                        <div className="mt-2 space-y-2">
                          {msg.sources.map((source, i) => {
                            const key = `${msg.id}-${i}`;
                            if (!expandedSources[key]) return null;
                            return (
                              <div
                                key={`${key}-preview`}
                                className="rounded border-2 border-nb-line bg-paper-subtle p-3 text-xs font-medium leading-relaxed text-ink-secondary"
                              >
                                <p className="mb-1 font-semibold text-ink">
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
                      className={`mt-2 font-mono text-[10px] ${
                        isUser
                          ? 'text-right text-ink-faint'
                          : msg.error
                            ? 'text-error-text'
                            : 'text-ink-muted'
                      }`}
                    >
                      {formatTime(msg.createdAt)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {showJumpToLatest && (
          <button
            type="button"
            onClick={jumpToLatest}
            aria-label="Jump to latest message"
            className="nb-icon-btn nb-focus absolute bottom-3 right-4 h-10 w-10 !bg-accent-orange"
          >
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Composer — hard-bordered block over the messages area */}
      <div className="shrink-0 px-4 pb-4 pt-2 sm:px-8">
        <div className="mx-auto w-full max-w-4xl">
        <div
          className={`flex items-end gap-2 rounded border-[3px] border-nb-line bg-paper-surface px-3 py-2 shadow-brutal ${
            loading || hasDocuments === false ? 'opacity-60' : ''
          }`}
        >
          <button
            type="button"
            onClick={() => chatFileInputRef.current?.click()}
            disabled={uploading}
            aria-label="Upload a document"
            title="Upload a PDF, DOCX or TXT document"
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-paper-surface text-ink transition-colors hover:bg-accent-yellow hover:text-ink-on-accent disabled:cursor-not-allowed ${
              uploading ? 'cursor-wait' : ''
            }`}
          >
            {uploading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Paperclip className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          <input
            ref={chatFileInputRef}
            name="chat-upload"
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleChatUpload}
            tabIndex={-1}
            className="sr-only"
          />
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              hasDocuments === false ? 'Upload a document first…' : 'Ask a question about your documents…'
            }
            disabled={loading || hasDocuments === false}
            aria-label="Your question"
            name="question"
            className="max-h-40 min-h-11 flex-1 resize-none bg-transparent py-2.5 text-sm leading-6 text-ink placeholder:text-ink-faint focus:outline-none disabled:cursor-not-allowed"
          />
          <WaveformOrb
            listening={listening}
            onClick={toggleVoice}
            label="Voice input"
          />
          {loading ? (
            <button
              type="button"
              onClick={stopStreaming}
              aria-label="Stop generating"
              title="Stop generating"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-accent-magenta text-ink-on-accent shadow-brutal-sm transition-transform active:translate-x-[3px] active:translate-y-[3px] active:shadow-none"
            >
              <Square className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => sendMessage()}
              disabled={!input.trim() || hasDocuments === false}
              aria-label="Send message"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-accent-yellow text-ink-on-accent shadow-brutal-sm transition-transform active:translate-x-[3px] active:translate-y-[3px] active:shadow-none disabled:cursor-not-allowed disabled:shadow-none disabled:opacity-40"
            >
              <Send className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
        {hasDocuments === false && (
          <p className="nb-label mt-2 text-center">
            Upload a document to start asking questions
          </p>
        )}
        <p className="mt-2 min-h-[2px]">
          {(uploadError || voiceError) && (
            <span className="block text-center font-mono text-[11px] font-bold uppercase tracking-wider text-error-text">
              {uploadError || voiceError}
            </span>
          )}
        </p>
        </div>
      </div>
    </div>
  );
}
