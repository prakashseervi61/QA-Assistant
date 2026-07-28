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

API_BASE_URL = "http://localhost:8000/api"
UPLOAD_TYPES = ["pdf", "docx", "txt"]
MAX_UPLOAD_SIZE_MB = 10
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


@st.cache_data(ttl=5)  # cache for 5 seconds
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
    """Render the sidebar with minimal necessary controls."""
    with st.sidebar:
        # Title block — centered
        st.markdown(
            "<div style='text-align:center; padding:0.5rem 0 0.25rem;'>"
            "<h2 style='margin:0; font-size:1.3rem;'>📚 QA Assistant</h2>"
            "<p style='margin:0; font-size:0.85rem; color:#6c757d;'>Document Q&A powered by RAG</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        # New conversation
        if st.button("➕ New Conversation", use_container_width=True, type="primary"):
            st.session_state.conversation_id = None
            st.session_state.messages = []
            st.rerun()

        # Conversation history
        conversations = fetch_conversations()
        if conversations:
            st.markdown("**Recent Conversations**")
            for conv in conversations[:5]:
                title = conv.get("title", "Untitled")[:20]
                conv_id = conv["id"]
                if st.button(title, key=f"hist_{conv_id}", use_container_width=True):
                    load_conversation(conv_id)
        else:
            st.caption("No conversations yet.")

        # Spacer pushes settings to bottom
        st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)

        # Settings (collapsible)
        with st.expander("⚙️ Settings", expanded=False):
            _render_settings()




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
        help=f"Supported formats: {', '.join(f.upper() for f in UPLOAD_TYPES)}. Max size: {MAX_UPLOAD_SIZE_MB} MB",
    )

    if uploaded_file is None:
        return

    # File size validation
    file_size_mb = uploaded_file.size / (1024 * 1024)
    if file_size_mb > MAX_UPLOAD_SIZE_MB:
        st.error(
            f"File too large ({file_size_mb:.1f} MB). Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB."
        )
        return

    # Show file details before uploading
    file_details = {
        "Filename": uploaded_file.name,
        "Size": f"{file_size_mb:.1f} MB",
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

    # Basic validation: ignore empty/whitespace-only input
    if not question.strip():
        st.warning("Please enter a question.")
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
                f"{API_BASE_URL}/query/stream",
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

    # Inject custom CSS for modern sidebar and responsive layout
    st.markdown(
        """
        <style>
        /* ---- Sidebar styling ---- */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
            border-right: 1px solid #e9ecef;
        }
        [data-testid="stSidebar"]::-webkit-scrollbar {
            width: 6px;
        }
        [data-testid="stSidebar"]::-webkit-scrollbar-thumb {
            background-color: rgba(0,0,0,0.15);
            border-radius: 3px;
        }
        /* Buttons inside sidebar */
        [data-testid="stSidebar"] .stButton>button {
            border-radius: 8px;
            font-weight: 500;
            transition: background-color 0.2s ease;
        }
        /* Dividers inside sidebar */
        [data-testid="stSidebar"] hr {
            margin: 0.4rem 0;
            border-color: #dee2e6;
        }
        /* Info/caption styling */
        [data-testid="stSidebar"] .stAlert,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            font-size: 0.82rem;
        }
        /* Expander styling */
        [data-testid="stSidebar"] .stExpander {
            border: none !important;
            box-shadow: none;
        }
        [data-testid="stSidebar"] .stExpanderHeader {
            font-weight: 600;
            color: #495057;
        }
        /* ---- Responsive layout ---- */
        @media (max-width: 640px) {
            .stColumns > div {
                flex: 1 1 100% !important;
                width: 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
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