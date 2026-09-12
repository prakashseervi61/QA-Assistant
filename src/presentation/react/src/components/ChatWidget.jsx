import { useEffect, useRef, useState } from 'react';
import { FiChevronDown, FiFileText, FiLoader, FiMessageSquare, FiMic, FiPaperclip, FiSend, FiSquare } from 'react-icons/fi';
import { fetchJSON, postFormData, streamChat } from '../api';

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

/** Best-effort title for a source chunk, falling back to "Source N". */
function getSourceTitle(source, index) {
  const meta = source.metadata || {};
  return meta.filename || meta.source || meta.title || `Source ${index + 1}`;
}

/** Generates a unique client-side message ID. */
function generateMessageId() {
  return `msg-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

// Storage access can throw in some contexts (Safari private mode, lockdowns);
// degrade gracefully instead of crashing the chat.
function safeGetItem(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable — fail silently */
  }
}

function safeRemoveItem(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* storage unavailable — fail silently */
  }
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

export default function ChatWidget({ conversationId: initialConversationId = null }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(initialConversationId);
  const [expandedSources, setExpandedSources] = useState({});
  const [hasDocuments, setHasDocuments] = useState(null); // null = still checking
  const [conversations, setConversations] = useState([]); // from GET /conversations
  const [restoring, setRestoring] = useState(true); // gates empty-state flash
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const chatFileInputRef = useRef(null); // hidden input for in-chat uploads
  const recognitionRef = useRef(null); // SpeechRecognition instance
  const abortRef = useRef(null); // AbortController for the in-flight stream
  const switchConversationRef = useRef(null); // latest switchConversation, for the Recent-view event listener
  const isSendingRef = useRef(false); // Execution lock preventing rapid double-send

  const LAST_CONVERSATION_KEY = 'qa-assistant.lastConversationId';
  const lastConversationId = () => safeGetItem(LAST_CONVERSATION_KEY);
  const saveLastConversationId = id => safeSetItem(LAST_CONVERSATION_KEY, id);
  const clearLastConversationId = () => safeRemoveItem(LAST_CONVERSATION_KEY);

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

  // Restore the most recent conversation (or the last one the user opened) on mount.
  useEffect(() => {
    let cancelled = false;
    fetchJSON('/conversations')
      .then(list => {
        if (cancelled) return undefined;
        setConversations(list);
        const savedId = lastConversationId();
        const target =
          savedId && list.some(conversation => conversation.id === savedId)
            ? savedId
            : (list[0]?.id ?? null);
        if (!target) return undefined;
        return fetchJSON(`/conversations/${target}`).then(msgs => {
          if (cancelled) return;
          setMessages(msgs.map(toLocalMessage));
          setConversationId(target);
          saveLastConversationId(target);
        });
      })
      .catch(() => {
        // Never lock the chat out; start fresh if restore fails.
        if (!cancelled) clearLastConversationId();
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Remember the active conversation across page reloads.
  useEffect(() => {
    if (conversationId) saveLastConversationId(conversationId);
  }, [conversationId]);

  // Scroll to the newest message when the conversation changes.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Abort any in-flight stream if the widget unmounts (e.g. mobile drawer close).
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Open a conversation selected from the Recent view (cross-component event).
  useEffect(() => {
    function handleOpenConversation(e) {
      const id = e.detail;
      if (id) switchConversationRef.current?.(id);
    }
    window.addEventListener('open-conversation', handleOpenConversation);
    return () => window.removeEventListener('open-conversation', handleOpenConversation);
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

  /** Silently refresh the conversation list (used after query/switch). */
  function refreshConversations() {
    fetchJSON('/conversations')
      .then(list => {
        setConversations(list);
        window.dispatchEvent(new CustomEvent('conversations-changed'));
      })
      .catch(() => {});
  }

  /** Load a different conversation into the panel, or reset to a fresh chat when id is empty. */
  async function switchConversation(id) {
    if (restoring || id === conversationId) return;
    // Stop any in-flight stream first so tokens can't bleed into the
    // conversation we're switching to.
    abortRef.current?.abort();
    if (!id) {
      setMessages([]);
      setConversationId(null);
      setExpandedSources({});
      clearLastConversationId();
      return;
    }
    setRestoring(true);
    try {
      const msgs = await fetchJSON(`/conversations/${id}`);
      setMessages(msgs.map(toLocalMessage));
      setConversationId(id);
      setExpandedSources({});
    } catch {
      /* keep current chat */
    } finally {
      setRestoring(false);
      refreshConversations();
    }
  }

  switchConversationRef.current = switchConversation;

  /** Immutably patch the message with the given `id` in the message list. */
  function updateMessageById(id, updater) {
    setMessages(prev => prev.map(msg => (msg.id === id ? updater(msg) : msg)));
  }

  /** Append streamed text to the assistant message with `id`. */
  function appendStreamText(id, text) {
    updateMessageById(id, msg => ({ ...msg, content: msg.content + text }));
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

    setInput('');
    resetTextareaHeight();

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
              doneEvent = event;
              if (event.conversation_id) {
                setConversationId(event.conversation_id);
                refreshConversations();
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
      abortRef.current = null;
      setLoading(false);
      isSendingRef.current = false;
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-paper">
      {/* Header */}
      {conversations.length > 0 && (
        <header className="flex shrink-0 items-center justify-end gap-3 border-b border-border bg-surface px-4 py-2.5 sm:px-6">
          <select
            id="conversation-select"
            name="conversation"
            aria-label="Previous chats"
            value={conversationId ?? ''}
            onChange={e => switchConversation(e.target.value)}
            disabled={restoring || loading}
            className="w-auto min-w-0 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-ink shadow-subtle focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60 sm:max-w-xs"
          >
            <option value="">New chat</option>
            {conversations.map(conversation => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title || 'New chat'}
              </option>
            ))}
          </select>
        </header>
      )}

      {/* Messages */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 && restoring ? (
          <div className="flex h-full flex-col items-center justify-center">
            <FiLoader className="h-6 w-6 animate-spin text-brand-600" aria-hidden="true" />
            <span className="sr-only">Loading conversation…</span>
          </div>
        ) : messages.length === 0 && !loading ? (
          hasDocuments === false ? (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-paper-200 text-stone-700">
                <FiPaperclip className="h-6 w-6" />
              </div>
              <h3 className="font-editorial text-lg font-medium text-ink">
                Upload a document to continue
              </h3>
              <p className="mt-1 max-w-xs text-sm leading-relaxed text-ink-muted">
                No documents are available yet. Upload a PDF, DOCX or TXT using the
                button below, or from the Documents view.
              </p>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-4 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-brand-100 bg-brand-50 text-brand-600 shadow-subtle">
                <FiMessageSquare className="h-6 w-6" />
              </div>
              <h3 className="font-editorial text-lg font-medium text-ink">Ask a question…</h3>
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
                      className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-xs font-medium text-ink-secondary shadow-subtle transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        ) : (
          <div role="log" aria-live="polite" className="mx-auto w-full max-w-4xl space-y-5 px-4 py-6 sm:px-8">
            {messages.map((msg, msgIndex) => {
              const isUser = msg.role === 'user';
              return (
                <div key={msg.id} className={`flex items-start gap-2.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
                  {!isUser && (
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-brand-200 bg-brand-100 font-serif text-xs font-bold text-brand-700">
                      Q
                    </div>
                  )}
                  <div
                    className={`${
                      isUser
                        ? 'max-w-[85%] rounded-2xl rounded-br-sm bg-stone-900 px-4 py-3 text-sm leading-relaxed text-[#fcfbf9] shadow-card'
                        : msg.error
                          ? 'max-w-[88%] rounded-2xl rounded-tl-sm border border-red-200 bg-red-50/90 px-4 py-3.5 text-sm leading-relaxed text-red-800 shadow-card'
                          : 'max-w-[88%] rounded-2xl rounded-tl-sm border border-border bg-surface px-4 py-3.5 text-sm leading-relaxed text-ink shadow-card'
                    }`}
                  >
                    {!isUser && msg.content === '' && loading ? (
                      <div className="flex items-center gap-1.5 py-1">
                        {[0, 1, 2].map(i => (
                          <span
                            key={i}
                            className="h-2 w-2 animate-bounce rounded-full bg-brand-500"
                            style={{ animationDelay: `${i * 150}ms` }}
                          />
                        ))}
                        <span className="sr-only">Assistant is thinking…</span>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}

                    {!isUser && msg.sources?.length > 0 && (
                      <div className="mt-3 border-t border-border pt-2.5">
                        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                          Referenced Sources
                        </p>
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
                                className={`inline-flex max-w-full items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                                  expanded
                                    ? 'border-brand-300 bg-brand-50 text-brand-700'
                                    : 'border-border bg-paper-200 text-ink-secondary hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
                                }`}
                              >
                                <FiFileText className="h-3 w-3 shrink-0" />
                                <span className="truncate">{getSourceTitle(source, i)}</span>
                                {score != null && (
                                  <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-muted">
                                    {score}%
                                  </span>
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
                            const key = `${msg.id}-${i}`;
                            if (!expandedSources[key]) return null;
                            return (
                              <div
                                key={`${key}-preview`}
                                className="rounded-lg border border-border bg-paper-200/80 p-3 text-xs leading-relaxed text-ink-secondary shadow-subtle"
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
                          ? 'text-right text-stone-400'
                          : msg.error
                            ? 'text-red-700'
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
        <div ref={messagesEndRef} />
      </div>

      {/* Composer — floating card over the messages area */}
      <div className="shrink-0 px-4 pb-4 pt-2 sm:px-8">
        <div className="mx-auto w-full max-w-4xl">
        <div
          className={`flex items-end gap-2 rounded-2xl border border-border bg-surface px-3.5 py-2.5 shadow-lg shadow-stone-900/5 transition-all focus-within:border-brand-600 focus-within:ring-2 focus-within:ring-brand-500 ${
            loading || hasDocuments === false ? 'opacity-60' : ''
          }`}
        >
          <button
            type="button"
            onClick={() => chatFileInputRef.current?.click()}
            disabled={uploading}
            aria-label="Upload a document"
            title="Upload a PDF, DOCX or TXT document"
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-brand-50 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed ${
              uploading ? 'cursor-wait text-brand-600' : ''
            }`}
          >
            {uploading ? (
              <FiLoader className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FiPaperclip className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          <input
            ref={chatFileInputRef}
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
            className="max-h-40 min-h-0 flex-1 resize-none bg-transparent py-1 text-sm text-ink placeholder:text-ink-faint focus:outline-none disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={toggleVoice}
            disabled={loading}
            aria-label={listening ? 'Stop voice input' : 'Start voice input'}
            title={listening ? 'Stop voice input' : 'Voice input'}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-50 ${
              listening ? 'bg-red-700 text-white hover:bg-red-800' : 'text-ink-muted hover:bg-brand-50 hover:text-brand-600'
            }`}
          >
            {listening ? (
              <FiMic className="h-4 w-4 animate-pulse" aria-hidden="true" />
            ) : (
              <FiMic className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          {loading ? (
            <button
              type="button"
              onClick={stopStreaming}
              aria-label="Stop generating"
              title="Stop generating"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-700 text-white shadow-subtle transition-colors hover:bg-red-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-1"
            >
              <FiSquare className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => sendMessage()}
              disabled={!input.trim() || hasDocuments === false}
              aria-label="Send message"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600 text-white shadow-subtle transition-colors hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-400"
            >
              <FiSend className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
        {hasDocuments === false && (
          <p className="mt-2 text-center font-mono text-[11px] text-ink-muted">
            Upload a document to start asking questions
          </p>
        )}
        <p className="mt-2 min-h-[2px]">
          {(uploadError || voiceError) && (
            <span className="block text-center font-mono text-[11px] text-red-600">
              {uploadError || voiceError}
            </span>
          )}
        </p>
        </div>
      </div>
    </div>
  );
}
