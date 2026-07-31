import { useEffect, useRef, useState } from 'react';
import {
  FiAlertCircle,
  FiFileText,
  FiLoader,
  FiRefreshCw,
  FiTrash2,
  FiUpload,
} from 'react-icons/fi';
import { fetchJSON, postFormData, deleteJSON } from '../api';

const ACCEPTED_TYPES = '.pdf,.docx,.txt';

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
    setFile(selected);
    setError(null);
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
    if (dropped) setFile(dropped);
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
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <FiFileText className="text-brand-600" />
          Documents
          {documents.length > 0 && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
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
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 ${
            dragging
              ? 'border-brand-500 bg-brand-50'
              : 'border-slate-300 bg-white hover:border-brand-400 hover:bg-brand-50/50'
          }`}
        >
          <input
            id="doc-file"
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileSelect}
            className="sr-only"
          />
          <FiUpload className={`h-7 w-7 ${dragging ? 'text-brand-600' : 'text-slate-400'}`} />
          <p className="mt-2 text-sm font-medium text-slate-700">
            Drag &amp; drop a file here, or <span className="text-brand-600">browse</span>
          </p>
          <p className="mt-1 text-xs text-slate-500">PDF, DOCX or TXT — one file at a time</p>
        </label>

        {file && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                <FiFileText className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-800">{file.name}</p>
                <p className="text-xs text-slate-500">{formatSize(file.size)}</p>
              </div>
            </div>
            <button
              type="submit"
              disabled={uploading}
              className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {uploading ? (
                <>
                  <FiLoader className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Uploading…
                </>
              ) : (
                <>
                  <FiUpload className="h-4 w-4" aria-hidden="true" />
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
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3"
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
            <div key={i} className="flex animate-pulse items-center gap-3 rounded-xl border border-slate-100 bg-white p-3">
              <div className="h-10 w-10 rounded-lg bg-slate-200" />
              <div className="flex-1 space-y-2">
                <div className="h-3 w-1/3 rounded bg-slate-200" />
                <div className="h-3 w-1/4 rounded bg-slate-200" />
              </div>
              <div className="h-6 w-16 rounded-full bg-slate-200" />
            </div>
          ))}
          <span className="sr-only">Loading documents…</span>
        </div>
      ) : documents.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
            <FiFileText className="h-6 w-6" />
          </div>
          <h3 className="mt-3 text-sm font-semibold text-slate-900">No documents yet</h3>
          <p className="mt-1 max-w-xs text-sm text-slate-500">
            Upload a PDF, DOCX or TXT file to start asking questions about it.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
          {documents.map(doc => {
            const name = doc.filename || doc.name || 'Unnamed';
            const size = doc.file_size ?? doc.size ?? 0;
            const chunks = doc.chunk_count ?? doc.chunks;
            return (
              <li key={doc.id} className="flex items-center gap-3 px-4 py-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <FiFileText className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-800">{name}</p>
                  <p className="text-sm text-slate-500">
                    {formatSize(size)}
                    {chunks != null && ` • ${chunks} chunks`}
                  </p>
                </div>
                <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
                  Ready
                </span>
                <button
                  type="button"
                  onClick={() => handleDelete(doc.id)}
                  aria-label={`Delete ${name}`}
                  className="rounded-md p-2 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
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
