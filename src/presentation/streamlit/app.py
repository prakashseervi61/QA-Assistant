"""QA Assistant - Streamlit Frontend

Main entry point for the Document Q&A Assistant UI.
Provides document upload, chat interface, and conversation history.
"""

import streamlit as st
import requests
import json
from typing import Generator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = "http://localhost:8000/api/v1"
UPLOAD_TYPES = ["pdf", "docx", "txt"]
API_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    """Initialise Streamlit session state variables."""
    defaults = {
        "conversation_id": None,
        "messages": [],
        "conversations": [],
        "llm_provider": "gemini",
        "top_k": 5,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def api_get(path: str, **kwargs) -> requests.Response | None:
    """Send a GET request to the API. Returns None on connection error."""
    try:
        return requests.get(f"{API_BASE_URL}{path}", timeout=API_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        return None


def api_post(path: str, **kwargs) -> requests.Response | None:
    """Send a POST request to the API. Returns None on connection error."""
    try:
        return requests.post(f"{API_BASE_URL}{path}", timeout=API_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        return None


def api_delete(path: str, **kwargs) -> requests.Response | None:
    """Send a DELETE request to the API. Returns None on connection error."""
    try:
        return requests.delete(f"{API_BASE_URL}{path}", timeout=API_TIMEOUT, **kwargs)
    except requests.ConnectionError:
        return None


def check_api_connection() -> bool:
    """Return True if the backend is reachable."""
    resp = api_get("/health")
    return resp is not None and resp.status_code == 200


# ---------------------------------------------------------------------------
# Conversation helpers
# ---------------------------------------------------------------------------


def fetch_conversations() -> list[dict]:
    """Fetch the conversation list from the API."""
    resp = api_get("/conversations")
    if resp and resp.status_code == 200:
        return resp.json()
    return []


def load_conversation(conversation_id: str) -> None:
    """Load a conversation's messages into session state."""
    resp = api_get(f"/conversations/{conversation_id}")
    if resp and resp.status_code == 200:
        raw_messages = resp.json()
        st.session_state.messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in raw_messages
        ]
    else:
        st.session_state.messages = []
    st.session_state.conversation_id = conversation_id
    st.rerun()


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation via the API and refresh the sidebar."""
    resp = api_delete(f"/conversations/{conversation_id}")
    if resp and resp.status_code == 200:
        if st.session_state.conversation_id == conversation_id:
            st.session_state.conversation_id = None
            st.session_state.messages = []
        st.session_state.conversations = fetch_conversations()
        st.rerun()
    else:
        st.toast("Failed to delete conversation.", icon="⚠️")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_sidebar() -> None:
    """Render the sidebar with branding, history, and settings."""
    with st.sidebar:
        st.markdown("## 📚 QA Assistant")
        st.caption("Document Q&A powered by RAG")
        st.markdown("---")

        # New conversation
        if st.button("➕ New Conversation", use_container_width=True):
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.rerun()

        st.markdown("---")

        # Conversation history
        st.subheader("💬 History")
        _render_conversation_history()

        st.markdown("---")

        # Settings
        _render_settings()

        st.markdown("---")

        # Connection indicator
        if check_api_connection():
            st.success("Backend connected")
        else:
            st.error("Backend unreachable")


def _render_conversation_history() -> None:
    """Render the scrollable conversation list inside the sidebar."""
    conversations = fetch_conversations()

    if not conversations:
        st.info("No conversations yet.")
        return

    for conv in conversations:
        title = conv.get("title", "Untitled")[:30]
        conv_id = conv["id"]

        col_label, col_del = st.columns([4, 1])
        with col_label:
            if st.button(title, key=f"conv_{conv_id}", use_container_width=True):
                load_conversation(conv_id)
        with col_del:
            if st.button("🗑️", key=f"del_{conv_id}"):
                delete_conversation(conv_id)


def _render_settings() -> None:
    """Render collapsible settings in the sidebar."""
    st.subheader("⚙️ Settings")

    with st.expander("Model Settings", expanded=False):
        st.selectbox(
            "LLM Provider",
            ["gemini", "openai", "anthropic"],
            key="llm_provider",
        )

        st.slider(
            "Top K Results",
            min_value=1,
            max_value=20,
            value=st.session_state.top_k,
            key="top_k",
        )


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------


def render_document_upload() -> None:
    """Render the document upload section."""
    st.header("📄 Upload Document")

    uploaded_file = st.file_uploader(
        "Choose a file",
        type=UPLOAD_TYPES,
        help=f"Supported formats: {', '.join(f.upper() for f in UPLOAD_TYPES)}",
    )

    if uploaded_file is None:
        return

    # Show file details before uploading
    file_details = {
        "Filename": uploaded_file.name,
        "Size": f"{uploaded_file.size / 1024:.1f} KB",
    }
    st.json(file_details)

    if st.button("Upload", use_container_width=True):
        with st.spinner("Uploading and processing..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
            resp = api_post("/documents/upload", files=files)

            if resp is None:
                st.error("Cannot reach the backend. Is the API server running?")
            elif resp.status_code == 200:
                data = resp.json()
                st.success(
                    f"✅ **{data.get('filename', uploaded_file.name)}** uploaded — "
                    f"{data.get('chunk_count', '?')} chunks created."
                )
            else:
                st.error(f"Upload failed ({resp.status_code}): {resp.text}")


# ---------------------------------------------------------------------------
# Chat interface
# ---------------------------------------------------------------------------


def render_chat_interface() -> None:
    """Render the main chat area with history and streaming input."""
    st.header("💬 Chat")

    # Show existing messages
    for message in st.session_state.messages:
        _render_message(message)

    # Chat input
    question = st.chat_input("Ask a question about your documents...")
    if not question:
        return

    # Append and display user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Stream assistant response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        try:
            payload = {
                "question": question,
                "conversation_id": st.session_state.conversation_id,
                "top_k": st.session_state.top_k,
            }

            with requests.post(
                f"{API_BASE_URL}/chat/query/stream",
                json=payload,
                stream=True,
                timeout=120,
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("data: "):
                        continue
                    raw = decoded[6:]
                    if raw == "[DONE]":
                        break

                    data = json.loads(raw)

                    if data["type"] == "chunk":
                        full_response += data["content"]
                        response_placeholder.markdown(full_response + "▌")

                    elif data["type"] == "done":
                        response_placeholder.markdown(full_response)
                        sources = data.get("sources", [])
                        st.session_state.conversation_id = data.get(
                            "conversation_id", st.session_state.conversation_id
                        )

                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": full_response,
                                "sources": sources,
                            }
                        )
                        if sources:
                            _render_sources(sources)

                    elif data["type"] == "error":
                        st.error(data.get("message", "Unknown error"))
                        return

        except requests.ConnectionError:
            st.error("Cannot reach the backend. Is the API server running?")
        except json.JSONDecodeError:
            st.error("Received malformed data from the server.")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")


def _render_message(message: dict) -> None:
    """Render a single chat message with optional source expander."""
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            _render_sources(message["sources"])


def _render_sources(sources: list[dict]) -> None:
    """Render source citations inside a collapsible expander."""
    with st.expander(f"📎 Sources ({len(sources)})", expanded=False):
        for i, source in enumerate(sources, 1):
            content = source.get("content", "")
            metadata = source.get("metadata", {})
            score = source.get("score", 0.0)
            filename = metadata.get("filename", "unknown")

            st.markdown(f"**Source {i}** — *{filename}* (relevance: {score:.2f})")
            st.text(content[:300] + ("..." if len(content) > 300 else ""))
            st.markdown("---")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Application entry point."""
    st.set_page_config(
        page_title="QA Assistant",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_session_state()

    render_sidebar()

    # Main content: documents on the left, chat on the right
    col_documents, col_chat = st.columns([1, 2])

    with col_documents:
        render_document_upload()

    with col_chat:
        render_chat_interface()


if __name__ == "__main__":
    main()
