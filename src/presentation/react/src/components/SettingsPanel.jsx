import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Database,
  Download,
  Eye,
  EyeOff,
  Gauge,
  KeyRound,
  MessageSquare,
  Palette,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { deleteJSON, fetchJSON, putJSON } from '../api';

/**
 * Settings — one scrolling page of divided sections.
 *
 * Structure follows the convention for settings pages: grouped sections with
 * dividers, each row showing its current state beside the label, and the
 * destructive actions isolated in a Danger Zone that is always last so a
 * destructive control never sits next to a routine one.
 *
 * Most rows are read-only on purpose. Nearly everything here is server-side
 * environment configuration, and a toggle that cannot actually change anything
 * would be worse than an honest read-only value. The one genuinely editable
 * thing — the API key — is a real control backed by a real endpoint.
 */

/** Human-readable byte size for the storage rows. */
function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** i;
  return `${value >= 10 || i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`;
}

/** A label/helper pair on the left and the current value on the right. */
function Row({ label, helper, children }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 border-t border-nb-line py-4 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-extrabold uppercase tracking-tight text-ink">{label}</p>
        {helper ? <p className="mt-1 text-sm text-ink-secondary">{helper}</p> : null}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/** Read-only value chip. */
function Value({ children, tone = 'neutral' }) {
  const toneClass =
    tone === 'on'
      ? '!bg-pastel-green'
      : tone === 'off'
        ? '!bg-paper-surface'
        : '!bg-paper-surface';
  return (
    <span className={`nb-chip font-mono text-[11px] uppercase ${toneClass}`}>{children}</span>
  );
}

/** On/off pill for a boolean setting. */
function Flag({ on, onLabel = 'On', offLabel = 'Off' }) {
  return (
    <span
      className={`nb-chip font-mono text-[11px] uppercase ${on ? '!bg-pastel-green' : '!bg-paper-surface'}`}
    >
      {on ? onLabel : offLabel}
    </span>
  );
}

/** A section heading with an icon and a heavy rule beneath it. */
function Section({ icon: Icon, title, description, children, tone }) {
  return (
    <section className="mt-12 first:mt-0">
      <div className="flex items-center gap-3">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded border-[3px] border-nb-line ${
            tone === 'danger' ? 'bg-accent-magenta text-ink-on-accent' : 'bg-accent-cyan text-ink-on-accent'
          }`}
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <h2 className="text-xl font-black uppercase tracking-tight text-ink sm:text-2xl">
          {title}
        </h2>
      </div>
      {description ? (
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-secondary">{description}</p>
      ) : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/**
 * Confirmation dialog for irreversible actions.
 *
 * Requires the user to type an exact phrase rather than just confirming a
 * dialog. Two apps in this space removed their lighter two-tap confirmation
 * because a stray double-click destroyed data, so the phrase is deliberate.
 */
function ConfirmDialog({ title, body, phrase, confirmLabel, busy, onCancel, onConfirm }) {
  const [typed, setTyped] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape' && !busy) onCancel();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onCancel]);

  const matches = typed.trim().toUpperCase() === phrase;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/70 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="w-full max-w-lg rounded border-[3px] border-nb-line bg-paper-surface p-6 shadow-brutal"
      >
        <h3 id="confirm-title" className="text-lg font-black uppercase text-ink">
          {title}
        </h3>
        <p className="mt-3 text-sm leading-relaxed text-ink-secondary">{body}</p>

        <label className="nb-label mt-5 block" htmlFor="confirm-phrase">
          Type <span className="font-mono text-ink">{phrase}</span> to confirm
        </label>
        <input
          id="confirm-phrase"
          ref={inputRef}
          value={typed}
          onChange={e => setTyped(e.target.value)}
          disabled={busy}
          autoComplete="off"
          spellCheck="false"
          className="nb-input nb-focus mt-2 w-full font-mono text-sm uppercase"
        />

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button type="button" onClick={onCancel} disabled={busy} className="nb-btn">
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!matches || busy}
            className="nb-btn nb-btn-danger"
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPanel({ isDark }) {
  const [config, setConfig] = useState(null);
  const [keyStatus, setKeyStatus] = useState(null);
  const [usage, setUsage] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const [keyDraft, setKeyDraft] = useState('');
  const [revealKey, setRevealKey] = useState(false);
  const [keyBusy, setKeyBusy] = useState(false);
  const [keyMessage, setKeyMessage] = useState(null);

  const [pendingAction, setPendingAction] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [cfg, key, usageData] = await Promise.all([
        fetchJSON('/settings'),
        fetchJSON('/settings/api-key'),
        fetchJSON('/usage?limit=5').catch(() => null),
      ]);
      setConfig(cfg);
      setKeyStatus(key);
      setUsage(usageData);
    } catch (err) {
      setLoadError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function saveKey() {
    setKeyBusy(true);
    setKeyMessage(null);
    try {
      const status = await putJSON('/settings/api-key', { api_key: keyDraft.trim() });
      setKeyStatus(status);
      setKeyDraft('');
      setRevealKey(false);
      setKeyMessage({ tone: 'ok', text: 'API key saved. It applies to the next question.' });
    } catch (err) {
      setKeyMessage({ tone: 'error', text: err.message });
    } finally {
      setKeyBusy(false);
    }
  }

  async function clearKey() {
    setKeyBusy(true);
    setKeyMessage(null);
    try {
      const status = await deleteJSON('/settings/api-key');
      setKeyStatus(status);
      setKeyDraft('');
      setKeyMessage({
        tone: 'ok',
        text:
          status.configured
            ? 'Removed. Now using the key from your .env file.'
            : 'Removed. No API key is configured — add one before asking a question.',
      });
    } catch (err) {
      setKeyMessage({ tone: 'error', text: err.message });
    } finally {
      setKeyBusy(false);
    }
  }

  function exportData() {
    // A plain navigation to the endpoint triggers a browser download, which
    // needs no blob handling and leaves the file exactly as the API built it.
    window.open('/api/export', '_blank', 'noopener');
    setActionMessage({ tone: 'ok', text: 'Export started — check your downloads.' });
  }

  async function runPendingAction() {
    const action = pendingAction;
    if (!action) return;
    setActionBusy(true);
    try {
      const result = await action.run();
      setActionMessage({ tone: 'ok', text: result });
      setPendingAction(null);
      await load();
      window.dispatchEvent(new CustomEvent('conversations-changed'));
      window.dispatchEvent(new CustomEvent('documents-changed'));
    } catch (err) {
      setActionMessage({ tone: 'error', text: err.message });
    } finally {
      setActionBusy(false);
    }
  }

  const deleteAllDocs = {
    title: 'Delete all documents?',
    body: 'This removes every uploaded document and all of its chunks from the vector store. Your conversations are kept. This cannot be undone — export your data first if you might want it back.',
    phrase: 'DELETE ALL DOCUMENTS',
    confirmLabel: 'Delete all documents',
    run: async () => {
      const result = await deleteJSON('/documents');
      return result.message ?? `Deleted ${result.deleted} document(s).`;
    },
  };

  const clearHistory = {
    title: 'Clear conversation history?',
    body: 'This permanently deletes every conversation and message. Your uploaded documents are kept. This cannot be undone — export your data first if you might want it back.',
    phrase: 'CLEAR ALL HISTORY',
    confirmLabel: 'Clear history',
    run: async () => {
      const result = await deleteJSON('/conversations');
      return result.message ?? `Deleted ${result.deleted} conversation(s).`;
    },
  };

  const keySourceLabel =
    keyStatus?.source === 'user'
      ? 'Added in Settings'
      : keyStatus?.source === 'env'
        ? 'From .env'
        : 'Not configured';

  return (
    <div className="mx-auto max-w-3xl pb-8">
      <span className="nb-tag">Settings</span>
      <h2 className="mt-4 text-3xl font-black uppercase text-ink sm:text-4xl">Configuration</h2>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-ink-secondary">
        Server settings are read from your <code className="font-mono">.env</code> at startup, so
        they are shown here as values rather than switches. The API key below is the one thing you
        can change from the browser.
      </p>

      {loadError ? (
        <p className="nb-card mt-6 border-error-border bg-error-bg p-4 text-sm text-error-text">
          Could not load settings: {loadError}
        </p>
      ) : null}

      {/* ---------------------------------------------------------------- */}
      <Section
        icon={Palette}
        title="Appearance"
        description="The theme toggle lives in the top bar so it is reachable from every view."
      >
        <Row label="Theme" helper="Paper beige or flat black — one token layer, no per-component overrides.">
          <Value>{isDark ? 'Dark' : 'Light'}</Value>
        </Row>
      </Section>

      {/* ---------------------------------------------------------------- */}
      <Section
        icon={MessageSquare}
        title="Retrieval"
        description="How answers are assembled. Changing any of these means editing .env and restarting."
      >
        <Row label="LLM provider" helper="Only Gemini is wired up.">
          <Value>{config?.llm_provider ?? '—'}</Value>
        </Row>
        <Row label="LLM model">
          <Value>{config?.llm_model ?? '—'}</Value>
        </Row>
        <Row label="Embeddings" helper="Computed locally — no API key, no data leaves the machine.">
          <Value>{config?.embedding_model ?? '—'}</Value>
        </Row>
        <Row label="Reranking" helper="A cross-encoder re-scores the top hits before generation.">
          <Flag on={config?.enable_reranking} />
        </Row>
        <Row label="Semantic chunking" helper="Split on meaning rather than fixed windows.">
          <Flag on={config?.enable_semantic_chunking} />
        </Row>
        <Row label="Hybrid search" helper="Blends dense vectors with BM25 keyword search.">
          <Flag on={config?.enable_hybrid_search} />
        </Row>
        <Row label="Guardrails" helper="PII and prompt-injection checks on input, groundedness on output.">
          <Flag on={config?.enable_guardrails} />
        </Row>
      </Section>

      {/* ---------------------------------------------------------------- */}
      <Section icon={Database} title="Storage" description="Everything lives on this machine.">
        <Row label="Documents">
          <Value>{config?.document_count ?? '—'}</Value>
        </Row>
        <Row label="Chunks indexed">
          <Value>{config?.chunk_count ?? '—'}</Value>
        </Row>
        <Row label="History file" helper={config?.history_db_path}>
          <Value>{formatBytes(config?.history_db_bytes)}</Value>
        </Row>
        <Row label="Upload limit">
          <Value>{config ? `${config.max_file_size_mb} MB` : '—'}</Value>
        </Row>
      </Section>

      {/* ---------------------------------------------------------------- */}
      <Section
        icon={Gauge}
        title="Usage"
        description="Token accounting for this process. Figures reset when the API restarts."
      >
        <Row label="Questions asked">
          <Value>{usage?.requests ?? '—'}</Value>
        </Row>
        <Row label="Tokens used">
          <Value>{usage?.total_tokens?.toLocaleString() ?? '—'}</Value>
        </Row>
        <Row label="Estimated cost">
          <Value>{usage ? `$${usage.est_cost_usd.toFixed(4)}` : '—'}</Value>
        </Row>
      </Section>

      {/* ---------------------------------------------------------------- */}
      <Section
        icon={KeyRound}
        title="API key"
        description="Use your own Gemini key instead of the one in .env. It takes effect on the next question — no restart needed."
      >
        <Row
          label="Active key"
          helper={
            keyStatus?.configured
              ? `Currently using the key ${keySourceLabel.toLowerCase()}.`
              : 'No API key is configured. Questions will fail until you add one.'
          }
        >
          {keyStatus?.configured ? (
            <span className="flex items-center gap-2">
              <Value>{keyStatus.masked}</Value>
              {keyStatus.source === 'user' ? (
                <button
                  type="button"
                  onClick={clearKey}
                  disabled={keyBusy}
                  className="nb-btn"
                >
                  Remove
                </button>
              ) : null}
            </span>
          ) : (
            <Value tone="off">None</Value>
          )}
        </Row>

        <div className="border-t border-nb-line py-4">
          <label className="nb-label block" htmlFor="api-key-input">
            {keyStatus?.source === 'user' ? 'Replace key' : 'Add a key'}
          </label>
          <div className="mt-2 flex flex-wrap gap-3">
            <div className="relative flex-1">
              <input
                id="api-key-input"
                type={revealKey ? 'text' : 'password'}
                value={keyDraft}
                onChange={e => setKeyDraft(e.target.value)}
                placeholder="AIza…"
                autoComplete="off"
                spellCheck="false"
                className="nb-input nb-focus w-full pr-12 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => setRevealKey(v => !v)}
                aria-label={revealKey ? 'Hide API key' : 'Show API key'}
                className="nb-icon-btn absolute right-2 top-1/2 -translate-y-1/2"
              >
                {revealKey ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>
            <button
              type="button"
              onClick={saveKey}
              disabled={keyBusy || keyDraft.trim().length < 8}
              className="nb-btn nb-btn-primary"
            >
              {keyBusy ? 'Saving…' : 'Save key'}
            </button>
          </div>
          <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-ink-secondary">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              Stored in plaintext at{' '}
              <code className="font-mono">{config?.secrets_file_path ?? 'data/secrets.json'}</code> on this machine — the same way your <code className="font-mono">.env</code> already
              holds a key. The file sits under <code className="font-mono">data/</code>, which is
              git-ignored, and the API only listens on loopback. It is never sent back to the
              browser; you only ever see the last four characters.
            </span>
          </p>
          {keyMessage ? (
            <p
              className={`mt-3 flex items-start gap-2 text-sm font-bold ${
                keyMessage.tone === 'error' ? 'text-error-text' : 'text-ink'
              }`}
            >
              {keyMessage.tone === 'ok' ? (
                <Check className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              <span>{keyMessage.text}</span>
            </p>
          ) : null}
        </div>
      </Section>

      {/* ---------------------------------------------------------------- */}
      <Section
        icon={AlertTriangle}
        tone="danger"
        title="Danger zone"
        description="Irreversible actions. Export your data first — there is no undo and no backup."
      >
        <div className="rounded border-[3px] border-nb-line bg-paper-surface p-5 shadow-brutal-sm">
          <Row label="Export everything" helper="Download all documents and conversations as JSON.">
            <button type="button" onClick={exportData} className="nb-btn">
              <Download className="h-4 w-4" aria-hidden="true" />
              Export
            </button>
          </Row>
          <Row
            label="Delete all documents"
            helper="Removes every document and its chunks. Conversations are kept."
          >
            <button
              type="button"
              onClick={() => {
                setActionMessage(null);
                setPendingAction(deleteAllDocs);
              }}
              className="nb-btn nb-btn-danger"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Delete all
            </button>
          </Row>
          <Row
            label="Clear conversation history"
            helper="Permanently removes every conversation and message. Documents are kept."
          >
            <button
              type="button"
              onClick={() => {
                setActionMessage(null);
                setPendingAction(clearHistory);
              }}
              className="nb-btn nb-btn-danger"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Clear history
            </button>
          </Row>

          {actionMessage ? (
            <p
              className={`mt-2 flex items-start gap-2 text-sm font-bold ${
                actionMessage.tone === 'error' ? 'text-error-text' : 'text-ink'
              }`}
            >
              {actionMessage.tone === 'ok' ? (
                <Check className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              <span>{actionMessage.text}</span>
            </p>
          ) : null}
        </div>
      </Section>

      <p className="mt-12 text-center font-mono text-[11px] uppercase tracking-wider text-ink-secondary">
        Marginalia v{config?.version ?? '0.1.0'}
      </p>

      {pendingAction ? (
        <ConfirmDialog
          title={pendingAction.title}
          body={pendingAction.body}
          phrase={pendingAction.phrase}
          confirmLabel={pendingAction.confirmLabel}
          busy={actionBusy}
          onCancel={() => setPendingAction(null)}
          onConfirm={runPendingAction}
        />
      ) : null}
    </div>
  );
}
