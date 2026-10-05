import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  CalendarClock,
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
import EmptyState from './EmptyState';
import { ErrorBanner, SkeletonGrid } from './ui';

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
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="nb-tag">Corpus</span>
          <h2 className="mt-4 flex items-center gap-3 text-3xl font-black uppercase text-ink sm:text-4xl">
            Documents
            {documents.length > 0 && (
                  <span className="nb-chip tabular-nums !bg-accent-yellow !text-ink-on-accent font-mono text-xs">
                {documents.length}
              </span>
            )}
          </h2>
        </div>
        <button
          type="button"
          onClick={loadDocs}
          aria-label="Refresh documents"
          className="nb-icon-btn nb-focus h-10 w-10 shrink-0"
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
            className="nb-card bg-paper-surface p-5"
            aria-label={`Preview ${selected.filename || 'document'}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3.5">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded border-[3px] border-nb-line bg-accent-yellow shadow-brutal-sm">
                  <FileText className="h-6 w-6 text-ink-on-accent" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-lg font-extrabold uppercase tracking-tight text-ink">
                    {selected.filename || selected.name || 'Unnamed'}
                  </p>
                  <p className="nb-label mt-1">{contentTypeLabel(selected)}</p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleDelete(selected.id)}
                  aria-label={`Delete ${selected.filename || 'document'}`}
                  className="nb-btn nb-focus !rounded !bg-error-bg !text-ink-on-accent !px-3 !py-1.5 !text-xs !font-bold hover:!bg-accent-magenta"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Delete
                </button>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  aria-label="Close preview"
                  className="nb-icon-btn nb-focus h-11 w-11"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>

            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded border-2 border-nb-line bg-paper-subtle px-3.5 py-3">
                <dt className="nb-label flex items-center gap-1.5">
                  <FileText className="h-3 w-3" aria-hidden="true" /> Size
                </dt>
                <dd className="mt-1.5 text-base font-extrabold tabular-nums text-ink">
                  {formatSize(selected.file_size ?? selected.size ?? 0)}
                </dd>
              </div>
              <div className="rounded border-2 border-nb-line bg-paper-subtle px-3.5 py-3">
                <dt className="nb-label flex items-center gap-1.5">
                  <Hash className="h-3 w-3" aria-hidden="true" /> Chunks
                </dt>
                <dd className="mt-1.5 text-base font-extrabold tabular-nums text-ink">
                  {selected.chunk_count ?? selected.chunks ?? 0}
                </dd>
              </div>
              <div className="rounded border-2 border-nb-line bg-paper-subtle px-3.5 py-3">
                <dt className="nb-label flex items-center gap-1.5">
                  <Info className="h-3 w-3" aria-hidden="true" /> Type
                </dt>
                <dd className="mt-1.5 text-base font-extrabold tabular-nums text-ink">{contentTypeLabel(selected)}</dd>
              </div>
              <div className="rounded border-2 border-nb-line bg-paper-subtle px-3.5 py-3">
                <dt className="nb-label flex items-center gap-1.5">
                  <CalendarClock className="h-3 w-3" aria-hidden="true" /> Added
                </dt>
                <dd className="mt-1.5 text-base font-extrabold tabular-nums text-ink">
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
          /* `nb-dropzone` pins every descendant's ink while the yellow ground is
             showing (drag or hover). Without it the children keep --ink-primary,
             which flips to paper in dark and drops to 1.25:1 on the yellow. */
          className="nb-dropzone flex cursor-pointer flex-col items-center justify-center rounded border-[3px] border-dashed border-nb-line bg-paper-surface px-6 py-12 text-center transition-colors hover:bg-accent-yellow"
          data-dragging={dragging ? 'true' : undefined}
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
            className="mb-4 flex h-14 w-14 items-center justify-center rounded border-[3px] border-nb-line bg-accent-cyan shadow-brutal-sm"
          >
            <UploadCloud className="h-7 w-7 text-ink" aria-hidden="true" />
          </motion.div>
          <p className="text-lg font-extrabold uppercase tracking-tight text-ink">
            Drop your document here
          </p>
          <p className="mt-2 text-sm font-medium text-ink-secondary">
            or <span className="font-bold text-ink underline decoration-4 underline-offset-2">browse</span> for a file
          </p>
          <p className="nb-label mt-4">PDF · DOCX · TXT — one at a time</p>
        </label>

        {file && (
          <div className="nb-card flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border-2 border-nb-line bg-pastel-cyan text-ink-on-accent">
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
              className="nb-btn nb-focus nb-btn-primary !px-4 !py-2 !text-sm"
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

      <ErrorBanner message={error} onRetry={loadDocs} />

      {/* Bento corpus — stats tile + document cards */}
      {loading ? (
        <SkeletonGrid label="Loading documents" />
      ) : documents.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload a PDF, DOCX or TXT file to start asking questions about it."
          hint="PDF · DOCX · TXT"
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="nb-card nb-tile-yellow flex flex-col justify-center gap-2 p-5">
              <p className="nb-label">Total size</p>
              <p className="text-3xl font-black tabular-nums text-ink-on-accent">
                {formatSize(totalSize)}
              </p>
            </div>
            <div className="nb-card nb-tile-cyan flex flex-col justify-center gap-2 p-5">
              <p className="nb-label">Indexed chunks</p>
              <p className="text-3xl font-black tabular-nums text-ink-on-accent">
                {totalChunks.toLocaleString()}
              </p>
            </div>
            <div className="nb-card nb-tile-pink flex flex-col justify-center gap-2 p-5">
              <p className="nb-label">Documents</p>
              <p className="text-3xl font-black tabular-nums text-ink-on-accent">
                {documents.length}
              </p>
            </div>
          </div>

          <ul className="nb-bento">
            {documents.map((doc, docIndex) => {
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
                    whileHover={{ x: -3, y: -3 }}
                    whileTap={{ x: 2, y: 2 }}
                    transition={{ type: 'spring', stiffness: 320, damping: 22 }}
                    className={`nb-card nb-card-hover w-full p-4 text-left ${
                      isSelected ? 'bg-accent-yellow' : ''
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Rotate the ground so no two adjacent cards share a
                          colour — the bento rule applied to the document list. */}
                      <div
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded border-2 border-nb-line ${
                          isSelected
                            ? 'bg-paper-surface'
                            : ['bg-pastel-green', 'bg-pastel-cyan', 'bg-pastel-yellow', 'bg-pastel-orange', 'bg-pastel-pink', 'bg-pastel-purple'][docIndex % 6]
                        }`}
                      >
                        <FileText className="h-5 w-5 text-ink" aria-hidden="true" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-extrabold uppercase tracking-tight text-ink">
                          {name}
                        </p>
                        <p className="mt-1 flex items-center gap-1.5 font-mono text-[11px] font-bold tabular-nums text-ink-secondary">
                          <span>{formatSize(size)}</span>
                          {chunks != null && (
                            <>
                              <span>•</span>
                              <span>{chunks} chunks</span>
                            </>
                          )}
                        </p>
                      </div>
                      {/* Arrow convention: bold directional arrows, never
                          chevrons. The card is a link to its own preview. */}
                      <span
                        className="mt-1 shrink-0 text-xl font-black leading-none text-ink transition-transform group-hover:translate-x-1"
                        aria-hidden="true"
                      >
                        →
                      </span>
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