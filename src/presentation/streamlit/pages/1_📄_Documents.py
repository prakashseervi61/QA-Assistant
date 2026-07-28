"""Document Management Page

Upload, view, and manage documents in the QA Assistant.
"""

import streamlit as st
import requests
import time

from src.presentation.streamlit.api_client import api_get, api_post, api_delete

UPLOAD_TYPES = ["pdf", "docx", "txt"]


# ---------------------------------------------------------------------------
# Cached data fetchers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=2, show_spinner=False)
def fetch_documents() -> list[dict]:
    """Fetch the list of documents from the API."""
    resp = api_get("/documents")
    if resp and resp.status_code == 200:
        data = resp.json()
        return data.get("documents", [])
    return []


# ---------------------------------------------------------------------------
# Upload section
# ---------------------------------------------------------------------------


def render_upload_section() -> None:
    """Render the document upload section."""
    st.header("📤 Upload Documents")

    uploaded_files = st.file_uploader(
        "Choose files to upload",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        help=f"Supported formats: {', '.join(f.upper() for f in UPLOAD_TYPES)}",
    )

    if not uploaded_files:
        return

    # Preview files
    st.subheader("Files to upload:")
    for file in uploaded_files:
        col_name, col_size, col_type = st.columns([4, 1, 1])
        with col_name:
            st.write(f"📄 {file.name}")
        with col_size:
            st.write(f"{file.size / 1024:.1f} KB")
        with col_type:
            st.write(file.type or "Unknown")

    # Upload button
    if st.button("Upload All", type="primary", use_container_width=True):
        _upload_files(uploaded_files)


def _upload_files(files) -> None:
    """Upload files to the API."""
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, file in enumerate(files):
        status_text.text(f"Uploading {file.name}...")

        try:
            file_dict = {"file": (file.name, file.getvalue())}
            resp = api_post("/documents/upload", files=file_dict)

            if resp is None:
                st.error(f"❌ {file.name}: Cannot reach backend")
            elif resp.status_code == 200:
                data = resp.json()
                chunks = data.get("chunk_count", "?")
                st.success(f"✅ {file.name} uploaded — {chunks} chunks created")
            else:
                st.error(f"❌ {file.name}: {resp.text}")

        except Exception as e:
            st.error(f"❌ {file.name}: {str(e)}")

        progress_bar.progress((i + 1) / len(files))

    status_text.text("Upload complete!")
    time.sleep(1)
    # Clear cached document list so the new upload appears
    fetch_documents.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# Documents list
# ---------------------------------------------------------------------------


def render_documents_list() -> None:
    """Render the list of uploaded documents."""
    st.header("📚 Uploaded Documents")

    documents = fetch_documents()

    if not documents:
        st.info("No documents uploaded yet. Upload your first document above!")
        return

    # Document table
    for doc in documents:
        col_name, col_size, col_chunks, col_delete = st.columns([4, 1, 1, 1])

        with col_name:
            filename = doc.get("filename", doc.get("name", "Unknown"))
            st.write(f"📄 {filename}")

        with col_size:
            file_size = doc.get("file_size", doc.get("size", 0))
            st.write(f"{file_size / 1024:.1f} KB")

        with col_chunks:
            chunk_count = doc.get("chunk_count", "?")
            st.write(f"{chunk_count} chunks")

        with col_delete:
            doc_id = doc.get("id", "")
            if st.button("🗑️", key=f"delete_{doc_id}"):
                _delete_document(doc_id)

        st.markdown("---")


def _delete_document(document_id: str) -> None:
    """Delete a document by ID."""
    resp = api_delete(f"/documents/{document_id}")

    if resp is None:
        st.error("Cannot reach backend")
    elif resp.status_code == 200:
        st.success("Document deleted!")
        fetch_documents.clear()  # clear cache after deletion
        st.rerun()
    else:
        st.error(f"Delete failed: {resp.text}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Documents page entry point."""
    st.set_page_config(
        page_title="Documents - QA Assistant",
        page_icon="📄",
        layout="wide",
    )

    # Sidebar navigation
    with st.sidebar:
        st.markdown("## 📚 QA Assistant")
        st.markdown("---")
        st.page_link("app.py", label="🏠 Home", icon="🏠")
        st.markdown("**📄 Documents**")
        st.page_link(
            "pages/2_💬_Chat.py",
            label="💬 Chat",
            icon="💬",
        )
        st.markdown("---")

    # Page content
    render_upload_section()
    st.markdown("---")
    render_documents_list()


if __name__ == "__main__":
    main()
