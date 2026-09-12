import { useEffect, useRef, useState } from 'react';
import {
  FiAlertCircle,
  FiFileText,
  FiLoader,
  FiRefreshCw,
  FiTrash2,
  FiUploadCloud,
} from 'react-icons/fi';
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

export default function DocumentList() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadDocs();
  }, []);

  async function loadDocs() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJSON('/documents');
      setDocuments(data.documents || data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleFileSelect(e) {
    const selected = e.target.files?.[0] || null;
    setError(null);
    if (!selected) return;
    if (!isAcceptedFile(selected)) {
      setError('Only PDF, DOCX and TXT files are supported');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    setFile(selected);
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

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-editorial flex items-center gap-2.5 text-2xl font-medium tracking-tight text-ink">
          <FiFileText className="text-brand-600" />
          Documents
          {documents.length > 0 && (
            <span className="rounded-full border border-border bg-paper-200 px-2 py-0.5 font-mono text-xs tabular-nums text-ink-secondary">
              {documents.length}
            </span>
          )}
        </h2>
      </div>

      {/* Upload form */}
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
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
            dragging
              ? 'border-brand-600 bg-brand-50 ring-2 ring-brand-400'
              : 'border-border bg-surface hover:border-brand-500 hover:bg-brand-50'
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
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600 shadow-subtle">
            <FiUploadCloud className="h-6 w-6" />
          </div>
          <p className="text-sm font-medium text-ink">
            Drag &amp; drop your document here, or <span className="font-medium text-brand-600 underline underline-offset-2">browse</span>
          </p>
          <p className="mt-1 font-mono text-xs text-ink-muted">PDF, DOCX or TXT — one file at a time</p>
        </label>

        {file && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3 shadow-card">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-100 bg-brand-50 text-brand-600">
                <FiFileText className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{file.name}</p>
                <p className="font-mono text-xs tabular-nums text-ink-muted">{formatSize(file.size)}</p>
              </div>
            </div>
            <button
              type="submit"
              disabled={uploading}
              className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-subtle transition-colors hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-stone-300"
            >
              {uploading ? (
                <>
                  <FiLoader className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Uploading…
                </>
              ) : (
                <>
                  <FiUploadCloud className="h-4 w-4" aria-hidden="true" />
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
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 shadow-subtle"
        >
          <p className="flex items-center gap-2 text-sm text-red-700">
            <FiAlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">{error}</span>
          </p>
          <button
            type="button"
            onClick={loadDocs}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            <FiRefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </button>
        </div>
      )}

      {/* Document list */}
      {loading ? (
        <div className="space-y-3" aria-label="Loading documents" role="status">
          {[0, 1, 2].map(i => (
            <div key={i} className="flex animate-pulse items-center gap-3 rounded-xl border border-border bg-surface p-3.5 shadow-subtle">
              <div className="h-10 w-10 rounded-lg bg-paper-300" />
              <div className="flex-1 space-y-2">
                <div className="h-3 w-1/3 rounded bg-paper-300" />
                <div className="h-3 w-1/4 rounded bg-paper-200" />
              </div>
              <div className="h-6 w-16 rounded-full bg-paper-300" />
            </div>
          ))}
          <span className="sr-only">Loading documents…</span>
        </div>
      ) : documents.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-surface px-6 py-12 text-center shadow-subtle">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl border border-border bg-paper-200 text-stone-600">
            <FiFileText className="h-6 w-6" />
          </div>
          <h3 className="font-editorial text-lg font-medium text-ink">No documents yet</h3>
          <p className="mt-1 max-w-xs text-sm leading-relaxed text-ink-muted">
            Upload a PDF, DOCX or TXT file to start asking questions about it.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-card">
          {documents.map(doc => {
            const name = doc.filename || doc.name || 'Unnamed';
            const size = doc.file_size ?? doc.size ?? 0;
            const chunks = doc.chunk_count ?? doc.chunks;
            return (
              <li key={doc.id} className="flex items-center gap-3.5 px-4 py-3.5 transition-colors hover:bg-paper-50/50">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-paper-200 text-stone-700">
                  <FiFileText className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{name}</p>
                  <p className="flex items-center gap-1.5 font-mono text-xs tabular-nums text-ink-muted">
                    <span>{formatSize(size)}</span>
                    {chunks != null && (
                      <>
                        <span className="text-ink-faint">•</span>
                        <span>{chunks} chunks</span>
                      </>
                    )}
                  </p>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-emerald-200/60 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
                  Ready
                </span>
                <button
                  type="button"
                  onClick={() => handleDelete(doc.id)}
                  aria-label={`Delete ${name}`}
                  className="rounded-lg p-2 text-stone-400 transition-colors hover:bg-red-50 hover:text-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                >
                  <FiTrash2 className="h-4 w-4" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
