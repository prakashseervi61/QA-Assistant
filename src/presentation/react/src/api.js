export const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api'; // proxied by Vite; override with VITE_API_BASE_URL

const AUTH_TOKEN_KEY = 'qa_assistant_token';

// Storage access can throw (Safari private mode, sandboxed iframes, enterprise
// lockdowns). Fail silently so auth/UX flows never crash over storage.
export function safeGetItem(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function safeSetItem(key, value) {
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

/**
 * Store (or clear, when passed null/undefined) the bearer token used for
 * authenticated requests. No-op storage-wise when no token is provided.
 */
export function setAuthToken(token) {
  if (token == null) {
    safeRemoveItem(AUTH_TOKEN_KEY);
  } else {
    safeSetItem(AUTH_TOKEN_KEY, token);
  }
}

/** Return the stored bearer token, or null when none has been set. */
export function getAuthToken() {
  return safeGetItem(AUTH_TOKEN_KEY);
}

/**
 * Merge caller-provided headers with defaults and, when a token is stored,
 * attach `Authorization: Bearer <token>`. No token => no Authorization header
 * (zero behavior change for existing users). An explicitly-provided
 * `Authorization` always wins over the stored token.
 */
function buildHeaders(headers = {}) {
  const merged = { ...headers };
  const token = getAuthToken();
  if (token && !merged.Authorization) {
    merged.Authorization = `Bearer ${token}`;
  }
  return merged;
}

export async function fetchJSON(endpoint, options = {}) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: buildHeaders({ 'Content-Type': 'application/json', ...options.headers }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

export async function postFormData(endpoint, formData) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    body: formData,
    headers: buildHeaders(),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

export async function deleteJSON(endpoint) {
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'DELETE',
    headers: buildHeaders({ 'Content-Type': 'application/json' }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Server-Sent Events (SSE) helpers
//
// The backend's POST /query/stream endpoint emits one `data:` JSON line per
// event followed by a blank line, and always terminates with the bare marker
// `data: [DONE]`. These helpers are pure and exported so they can be unit
// tested in isolation.
// ---------------------------------------------------------------------------

/**
 * Parse a single SSE line (without its trailing newline) into a token.
 *
 * Returns one of:
 *   { kind: 'blank' }            — empty line (ends an event block)
 *   { kind: 'done' }             — `data: [DONE]` stream-end marker
 *   { kind: 'data', value }      — `data: <payload>` line
 *   { kind: 'comment'|'ignored'} — `:` comment or any other line type
 */
export function parseSSELine(line) {
  if (line === '') return { kind: 'blank' };
  if (line.startsWith(':')) return { kind: 'comment' };
  // Non-`data:` lines (`event:`, `id:`, `retry:`, ...) are intentionally
  // ignored: the current backend contract only ever emits `data:` lines.
  if (!line.startsWith('data:')) return { kind: 'ignored' };
  const value = line.slice('data:'.length);
  const payload = value.startsWith(' ') ? value.slice(1) : value;
  if (payload === '[DONE]') return { kind: 'done' };
  return { kind: 'data', value: payload };
}

/**
 * Parse the raw lines of a single SSE event block (lines up to and including
 * the preceding blank line) into a structured event.
 *
 * Returns:
 *   { type: 'end' }                        — `data: [DONE]` marker
 *   { type: '<event.type>', data }         — parsed JSON payload, dispatched
 *                                            on its `type` field (chunk/done/
 *                                            error, or any other value)
 *   { type: 'json', data }                 — parsed JSON without a `type` field
 *   null                                   — block had no usable data lines
 */
export function parseSSEEvent(lines) {
  let sawDone = false;
  const payloads = [];
  for (const line of lines) {
    const token = parseSSELine(line);
    if (token.kind === 'done') sawDone = true;
    else if (token.kind === 'data') payloads.push(token.value);
  }
  if (sawDone) return { type: 'end' };
  if (payloads.length === 0 || payloads.every(payload => payload.trim() === '')) {
    return null;
  }
  let data;
  try {
    data = JSON.parse(payloads.join('\n'));
  } catch {
    return null; // non-JSON payload (or empty data) — nothing to dispatch
  }
  if (data && typeof data === 'object' && typeof data.type === 'string') {
    return { type: data.type, data };
  }
  return { type: 'json', data };
}

/**
 * Stream a document query from POST /query/stream (Server-Sent Events).
 *
 * The backend emits one `data:` JSON line per event, each with a `type` field:
 *   { "type": "chunk", "content": "<incremental text>" }
 *   { "type": "done", "answer": "...", "sources": [...],
 *     "conversation_id": "...", "message_id": "..." }
 *   { "type": "error", "message": "<reason>" }
 * ...and always terminates with the bare marker `data: [DONE]`.
 *
 * Every parsed JSON payload is passed to `onEvent` (chunk/done/error alike).
 * Resolves when the `[DONE]` marker arrives or the stream closes. Rejects on
 * non-OK HTTP status or transport errors. When the caller aborts via `signal`,
 * the in-flight read rejects (AbortError) — distinguish a user-initiated stop
 * by checking `signal.aborted` at the call site.
 */
export async function streamChat(payload, { signal, onEvent } = {}) {
  const res = await fetch(`${API_BASE_URL}/query/stream`, {
    method: 'POST',
    headers: buildHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    let detail = '';
    try {
      detail = await res.text();
    } catch {
      /* non-text error body — fall through */
    }
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  if (!res.body) {
    throw new Error('Streaming is not supported by this browser');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Process complete event blocks (separated by blank lines).
    let separatorIndex;
    while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const event = parseSSEEvent(block.split('\n'));
      if (event && event.type === 'end') {
        // `[DONE]` marker — stop consuming; release the connection.
        reader.cancel().catch(() => {});
        return;
      }
      if (event && typeof onEvent === 'function') onEvent(event.data);
    }
  }

  // Flush any trailing block that never got a closing blank line.
  if (buffer.length > 0) {
    const event = parseSSEEvent(buffer.split('\n'));
    if (event && event.type !== 'end' && typeof onEvent === 'function') {
      onEvent(event.data);
    }
  }
}