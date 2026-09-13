import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  CalendarClock,
  ChevronRight,
  FileText,
  Hash,
  Info,
  Loader2,
  RefreshCw,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { fetchJSON, postFormData, deleteJSON } from '../api';

const ACCEPTED_TYPES = '.pdf,.docx,.txt';

// Allowed extensions with their canonical MIME types. The final value may be
// a comma-separated list (as `application/vnd.openxmlformats-...` has aliases).
const ACCEPTED_MIME_BY_EXT = {
  '.pdf': 'application/pdf',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.txt': 'text/plain',
};

function getExtension(filename) {
  const dot = filename.lastIndexOf('.');
  return dot === -1 ? undefined : filename.slice(dot).toLowerCase();
}

/**
 * Defense-in-depth for dragged-in files: the accept attribute only constrains
 * the native picker, so validate dropped/picked files before they're uploaded.
 */
function isAcceptedFile(file) {
  const ext = getExtension(file.name);
  if (!ext || !(ext in ACCEPTED_MIME_BY_EXT)) return false;
  const expected = ACCEPTED_MIME_BY_EXT[ext];
  // Accept when the browser reports no/correct type; reject a clear mismatch
  // (some upload controls may report generic types, so allow those).
  return (
    file.type === '' ||
    file.type === expected ||
    file.type.startsWith('text/') ||
    file.type === 'application/octet-stream'
  );
}

/** Format a byte count as a human-readable size (B / KB / MB / GB). */
function formatSize(bytes) {
  const size = Number(bytes);
  if (!Number.isFinite(size) || size <= 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const rounded = value >= 10 || unitIndex === 0 ? Math.round(value) : value.toFixed(1);
  return `${rounded} ${units[unitIndex]}`;
}

/** Render an ISO timestamp as a short date (or a dash when unparseable). */
function formatShortDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Human-readable content type label (fall back to the raw MIME value). */
function contentTypeLabel(doc) {
  const raw = doc.content_type || doc.mime_type || '';
  if (raw.includes('pdf')) return 'PDF';
  if (raw.includes('word') || raw.includes('docx')) return 'DOCX';
  if (raw.startsWith('text') || raw.includes('txt')) return 'TXT';
  return raw ? raw.split('/').pop().toUpperCase() : 'DOC';
}

export default function DocumentList() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [selected, setSelected] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadDocs();
  }, []);

  async function loadDocs() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJSON('/documents');
      const list = data.documents || data || [];
      setDocuments(Array.isArray(list) ? list : []);
      // Drop the preview if its document disappeared (e.g. after a delete).
      setSelected(prev => (prev && list.some(doc => doc.id === prev.id) ? prev : null));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleFileSelect(e) {
    const selectedFile = e.target.files?.[0] || null;
    setError(null);
    if (!selectedFile) return;
    if (!isAcceptedFile(selectedFile)) {
      setError('Only PDF, DOCX and TXT files are supported');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    setFile(selectedFile);
  }

  function handleDragOver(e) {
    e.preventDefault();
    setDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0] || null;
    if (!dropped) return;
    if (!isAcceptedFile(dropped)) {
      setError('Only PDF, DOCX and TXT files are supported');
      return;
    }
    setFile(dropped);
  }

  async function handleUpload(e) {
    e.preventDefault();
    if (!file || uploading) return;
    setUploading(true);
    setError(null);

    // Single file under the `file` field — matches the backend contract.
    const formData = new FormData();
    formData.append('file', file);

    try {
      await postFormData('/documents/upload', formData);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await loadDocs();
      window.dispatchEvent(new CustomEvent('documents-changed'));
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this document?')) return;
    try {
      await deleteJSON(`/documents/${id}`);
      await loadDocs();
      window.dispatchEvent(new CustomEvent('documents-changed'));
    } catch (err) {
      setError(err.message);
    }
  }

  const totalSize = documents.reduce((sum, doc) => sum + (doc.file_size ?? doc.size ?? 0), 0);
  const totalChunks = documents.reduce(
    (sum, doc) => sum + (doc.chunk_count ?? doc.chunks ?? 0),
    0
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-editorial flex items-center gap-2.5 text-2xl font-medium tracking-tight text-ink">
          <span className="bg-bioluminescent flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow-violet">
            <FileText className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
          Documents
          {documents.length > 0 && (
            <span className="rounded-full border border-border bg-paper-200 px-2 py-0.5 font-mono text-xs tabular-nums text-ink-secondary">
              {documents.length}
            </span>
          )}
        </h2>
        <button
          type="button"
          onClick={loadDocs}
          aria-label="Refresh documents"
          className="glass rounded-lg p-2 text-ink-muted transition-all hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
        </button>
      </div>

      {/* Fold-in preview panel for the selected document */}
      <AnimatePresence>
        {selected && (
          <motion.section
            key="doc-preview"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 320, damping: 26 }}
            className="glass-strong rounded-2xl p-5 shadow-float"
            aria-label={`Preview ${selected.filename || 'document'}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3.5">
                <div className="bg-bioluminescent flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white shadow-glow-violet">
                  <FileText className="h-6 w-6" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-base font-semibold text-ink">
                    {selected.filename || selected.name || 'Unnamed'}
                  </p>
                  <p className="mt-0.5 font-mono text-xs uppercase tracking-wider text-ink-faint">
                    {contentTypeLabel(selected)}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleDelete(selected.id)}
                  aria-label={`Delete ${selected.filename || 'document'}`}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-paper-100 px-3 py-1.5 text-xs font-medium text-ink-secondary transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Delete
                </button>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  aria-label="Close preview"
                  className="glass rounded-lg p-2 text-ink-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>

            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-border bg-paper-100 px-3.5 py-3">
                <dt className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  <FileText className="h-3 w-3" aria-hidden="true" /> Size
                </dt>
                <dd className="mt-1 text-sm font-medium tabular-nums text-ink">
                  {formatSize(selected.file_size ?? selected.size ?? 0)}
                </dd>
              </div>
              <div className="rounded-xl border border-border bg-paper-100 px-3.5 py-3">
                <dt className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  <Hash className="h-3 w-3" aria-hidden="true" /> Chunks
                </dt>
                <dd className="mt-1 text-sm font-medium tabular-nums text-ink">
                  {selected.chunk_count ?? selected.chunks ?? 0}
                </dd>
              </div>
              <div className="rounded-xl border border-border bg-paper-100 px-3.5 py-3">
                <dt className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  <Info className="h-3 w-3" aria-hidden="true" /> Type
                </dt>
                <dd className="mt-1 text-sm font-medium text-ink">{contentTypeLabel(selected)}</dd>
              </div>
              <div className="rounded-xl border border-border bg-paper-100 px-3.5 py-3">
                <dt className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                  <CalendarClock className="h-3 w-3" aria-hidden="true" /> Added
                </dt>
                <dd className="mt-1 text-sm font-medium text-ink">
                  {formatShortDate(selected.created_at)}
                </dd>
              </div>
            </dl>
          </motion.section>
        )}
      </AnimatePresence>

      {/* Upload dropzone */}
      <form onSubmit={handleUpload} className="space-y-3">
        <label
          htmlFor="doc-file"
          role="button"
          tabIndex={0}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`glass flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed px-6 py-10 text-center transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
            dragging
              ? 'border-brand-500 shadow-glow-violet'
              : 'border-glass-border hover:border-brand-400 hover:shadow-card-hover'
          }`}
        >
          <input
            id="doc-file"
            name="file-upload"
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileSelect}
            tabIndex={-1}
            className="sr-only"
          />
          <motion.div
            animate={dragging ? { scale: 1.08, rotate: -2 } : { scale: 1, rotate: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 18 }}
            className="bg-bioluminescent mb-3 flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-glow-violet"
          >
            <UploadCloud className="h-6 w-6" aria-hidden="true" />
          </motion.div>
          <p className="text-sm font-medium text-ink">
            Drag &amp; drop your document here, or{' '}
            <span className="font-medium text-brand-500 underline underline-offset-2">
              browse
            </span>
          </p>
          <p className="mt-1 font-mono text-xs text-ink-faint">
            PDF, DOCX or TXT — one file at a time
          </p>
        </label>

        {file && (
          <div className="glass-strong flex items-center justify-between gap-3 rounded-2xl px-4 py-3 shadow-card">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-paper-100 text-brand-500">
                <FileText className="h-5 w-5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{file.name}</p>
                <p className="font-mono text-xs tabular-nums text-ink-faint">{formatSize(file.size)}</p>
              </div>
            </div>
            <button
              type="submit"
              disabled={uploading}
              className="bg-bioluminescent inline-flex shrink-0 items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-glow-violet transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Uploading…
                </>
              ) : (
                <>
                  <UploadCloud className="h-4 w-4" aria-hidden="true" />
                  Upload
                </>
              )}
            </button>
          </div>
        )}
      </form>

      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-error-border bg-error-bg px-4 py-3 shadow-subtle"
        >
          <p className="flex items-center gap-2 text-sm text-error-text">
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">{error}</span>
          </p>
          <button
            type="button"
            onClick={loadDocs}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-error-border bg-paper-100 px-3 py-1.5 text-xs font-medium text-error-text transition-colors hover:bg-error-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </button>
        </div>
      )}

      {/* Bento corpus — stats tile + document cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading documents" role="status">
          {[0, 1, 2, 3, 4, 5].map(i => (
            <div key={i} className="glass animate-pulse rounded-2xl p-4">
              <div className="h-10 w-10 rounded-xl bg-paper-300" />
              <div className="mt-3 space-y-2">
                <div className="h-3 w-2/3 rounded bg-paper-300" />
                <div className="h-3 w-1/3 rounded bg-paper-200" />
              </div>
            </div>
          ))}
          <span className="sr-only">Loading documents…</span>
        </div>
      ) : documents.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-3xl border-2 border-dashed border-glass-border bg-glass px-6 py-12 text-center shadow-card">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-paper-100 text-ink-faint">
            <FileText className="h-6 w-6" aria-hidden="true" />
          </div>
          <h3 className="font-editorial text-lg font-medium text-ink">No documents yet</h3>
          <p className="mt-1 max-w-xs text-sm leading-relaxed text-ink-muted">
            Upload a PDF, DOCX or TXT file to start asking questions about it.
          </p>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="mt-4 text-sm font-medium text-brand-500 underline underline-offset-2 hover:text-brand-400"
          >
            Choose a file to upload
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="glass flex flex-col justify-center gap-2 rounded-2xl p-5 shadow-card">
              <p className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                Total size
              </p>
              <p className="font-editorial text-2xl font-semibold tracking-tight text-ink tabular-nums">
                {formatSize(totalSize)}
              </p>
            </div>
            <div className="glass flex flex-col justify-center gap-2 rounded-2xl p-5 shadow-card">
              <p className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                Indexed chunks
              </p>
              <p className="font-editorial text-2xl font-semibold tracking-tight text-ink tabular-nums">
                {totalChunks.toLocaleString()}
              </p>
            </div>
            <div className="glass flex flex-col justify-center gap-2 rounded-2xl p-5 shadow-card">
              <p className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                Documents
              </p>
              <p className="font-editorial text-2xl font-semibold tracking-tight text-ink tabular-nums">
                {documents.length}
              </p>
            </div>
          </div>

          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {documents.map(doc => {
              const name = doc.filename || doc.name || 'Unnamed';
              const size = doc.file_size ?? doc.size ?? 0;
              const chunks = doc.chunk_count ?? doc.chunks;
              const isSelected = selected?.id === doc.id;
              return (
                <li key={doc.id}>
                  <motion.button
                    type="button"
                    onClick={() => setSelected(isSelected ? null : doc)}
                    aria-label={`Preview ${name}`}
                    aria-pressed={isSelected}
                    whileHover={{ y: -3 }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ type: 'spring', stiffness: 320, damping: 22 }}
                    className={`glass w-full rounded-2xl p-4 text-left shadow-card transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                      isSelected ? 'ring-2 ring-brand-500 shadow-glow-violet' : ''
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-paper-100 text-brand-500">
                        <FileText className="h-5 w-5" aria-hidden="true" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">{name}</p>
                        <p className="mt-0.5 flex items-center gap-1.5 font-mono text-xs tabular-nums text-ink-faint">
                          <span>{formatSize(size)}</span>
                          {chunks != null && (
                            <>
                              <span>•</span>
                              <span>{chunks} chunks</span>
                            </>
                          )}
                        </p>
                      </div>
                      <ChevronRight
                        className={`mt-1 h-4 w-4 shrink-0 text-ink-faint transition-transform ${
                          isSelected ? 'rotate-90' : ''
                        }`}
                        aria-hidden="true"
                      />
                    </div>
                  </motion.button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}