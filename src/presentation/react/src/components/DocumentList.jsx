import { useEffect, useState } from 'react';
import { FaRegFileAlt, FaEllipsisV } from 'react-icons/fa';
import { fetchJSON, postFormData, deleteJSON } from '../api';

export default function DocumentList() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDocs();
  }, []);

  async function loadDocs() {
    setLoading(true);
    try {
      const data = await fetchJSON('/documents');
      setDocuments(data.documents || data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(e) {
    e.preventDefault();
    const fileInput = document.getElementById('doc-file');
    const files = fileInput.files;
    if (!files.length) return;
    setUploading(true);
    const formData = new FormData();
    Array.from(files).forEach(file => {
      formData.append('files', file);
    });
    try {
      const resp = await postFormData('/documents/upload', formData);
      // optimistic update: we could refetch
      await loadDocs();
      fileInput.value = '';
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
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) return <p className="text-center py-4">Loading documents…</p>;
  if (error) return <p className="text-red-500 text-center py-4">{error}</p>;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold flex items-center space-x-2">
        <FaRegFileAlt /> Documents
      </h2>

      {/* Upload Form */}
      <form onSubmit={handleUpload} className="flex flex-col space-y-2">
        <label className="flex items-center space-x-2">
          <input
            type="file"
            id="doc-file"
            multiple
            accept=".pdf,.docx,.pptx,.txt"
            className="flex-1 border rounded px-3 py-2"
          />
          <button
            type="submit"
            disabled={uploading}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </label>
      </form>

      {/* Document List */}
      <div className="divide-y">
        {documents.length === 0 ? (
          <p className="text-center py-4 text-gray-500">No documents uploaded yet.</p>
        ) : (
          documents.map(doc => (
            <div key={doc.id} className="flex items-center py-3">
              <div className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-gray-100 rounded">
                <FaRegFileAlt className="text-gray-600" />
              </div>
              <div className="flex-1 ml-3">
                <p className="font-medium">{doc.filename || doc.name || 'Unnamed'}</p>
                <p className="text-sm text-gray-500">
                  {(doc.size || doc.file_size || 0) / 1024}.1f KB • {doc.chunk_count || doc.chunks || '?'} chunks
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs rounded">Ready</span>
                <button
                  onClick={() => handleDelete(doc.id)}
                  className="text-gray-400 hover:text-gray-600"
                  aria-label="More actions"
                >
                  <FaEllipsisV />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}