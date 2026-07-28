"""Chat Page

Interactive chat interface for querying documents with streaming responses.
Standalone Streamlit multipage page — navigable from the sidebar.
"""

import streamlit as st
import requests
import json

from src.presentation.streamlit.api_client import api_get, api_post, API_BASE_URL, API_TIMEOUT
from src.presentation.streamlit.components import render_sources

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def init_chat_session() -> None:
    """Initialise chat-specific session state variables."""
    defaults = {
        "chat_messages": [],
        "current_conversation": None,
        "top_k": 5,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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
    """Load a conversation's messages into session state and rerun."""
    if st.session_state.current_conversation == conversation_id:
        return

    resp = api_get(f"/conversations/{conversation_id}")
    if resp and resp.status_code == 200:
        raw_messages = resp.json()
        st.session_state.current_conversation = conversation_id
        st.session_state.chat_messages = [
            {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "sources": msg.get("sources", []),
            }
            for msg in raw_messages
        ]
        st.rerun()
    else:
        st.toast("Failed to load conversation.", icon="\u26a0\ufe0f")


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation via the API and refresh."""
    try:
        resp = requests.delete(
            f"{API_BASE_URL}/conversations/{conversation_id}",
            timeout=API_TIMEOUT,
        )
    except requests.ConnectionError:
        st.toast("Cannot reach backend.", icon="\u26a0\ufe0f")
        return

    if resp.status_code == 200:
        if st.session_state.current_conversation == conversation_id:
            st.session_state.current_conversation = None
            st.session_state.chat_messages = []
        st.rerun()
    else:
        st.toast("Failed to delete conversation.", icon="\u26a0\ufe0f")


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------


def render_chat_header() -> None:
    """Render page header with conversation selector and new-conversation button."""
    st.header("\U0001f4ac Document Chat")

    col_list, col_new, col_del = st.columns([5, 1, 1])

    with col_list:
        conversations = fetch_conversations()
        options = ["\u2795 New Conversation"] + [
            conv.get("title", f"Conversation {conv['id'][:8]}")
            for conv in conversations
        ]

        selected = st.selectbox(
            "Conversation",
            options,
            key="conversation_selector",
            label_visibility="collapsed",
        )

        if selected != "\u2795 New Conversation":
            idx = options.index(selected) - 1
            if 0 <= idx < len(conversations):
                load_conversation(conversations[idx]["id"])

    with col_new:
        if st.button("\u2795 New", use_container_width=True):
            st.session_state.current_conversation = None
            st.session_state.chat_messages = []
            st.rerun()

    with col_del:
        if st.session_state.current_conversation:
            if st.button("\U0001f5d1\ufe0f", use_container_width=True):
                delete_conversation(st.session_state.current_conversation)


def render_chat_messages() -> None:
    """Render the full chat message history."""
    for idx, message in enumerate(st.session_state.chat_messages):
        role = message["role"]
        with st.chat_message(role):
            st.markdown(message["content"])
            if message.get("sources"):
                render_sources(message["sources"], key_suffix=f"{idx}")


# ---------------------------------------------------------------------------
# Streaming chat input
# ---------------------------------------------------------------------------


def render_chat_input() -> None:
    """Render the chat input box and handle streaming responses."""
    question = st.chat_input("Ask a question about your documents...")
    if not question:
        return

    # Append and display user message immediately
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Stream assistant response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        sources: list[dict] = []

        try:
            payload = {
                "question": question,
                "conversation_id": st.session_state.current_conversation,
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
                        response_placeholder.markdown(full_response + "\u258c")

                    elif data["type"] == "done":
                        response_placeholder.markdown(full_response)
                        sources = data.get("sources", [])
                        st.session_state.current_conversation = data.get(
                            "conversation_id",
                            st.session_state.current_conversation,
                        )
                        if sources:
                            render_sources(sources, key_suffix="new")

                    elif data["type"] == "error":
                        error_msg = data.get("message", "Unknown error")
                        response_placeholder.markdown("")
                        st.error(f"Error: {error_msg}")
                        return

        except requests.ConnectionError:
            response_placeholder.markdown("")
            st.error("Cannot reach the backend. Is the API server running?")
            return
        except json.JSONDecodeError:
            response_placeholder.markdown("")
            st.error("Received malformed data from the server.")
            return
        except Exception as exc:
            response_placeholder.markdown("")
            st.error(f"Unexpected error: {exc}")
            return

    # Persist assistant message after streaming completes
    st.session_state.chat_messages.append(
        {
            "role": "assistant",
            "content": full_response,
            "sources": sources,
        }
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Chat page entry point."""
    st.set_page_config(
        page_title="Chat - QA Assistant",
        page_icon="\U0001f4ac",
        layout="wide",
    )

    # Sidebar navigation
    with st.sidebar:
        st.markdown("## \U0001f4da QA Assistant")
        st.markdown("---")
        st.page_link("app.py", label="\U0001f3e0 Home", icon="\U0001f3e0")
        st.page_link(
            "pages/1_📄_Documents.py",
            label="📄 Documents",
            icon="📄",
        )
        st.markdown("**\U0001f4ac Chat**")
        st.markdown("---")

        resp = api_get("/health")
        if resp is not None and resp.status_code == 200:
            st.success("Backend connected")
        else:
            st.error("Backend unreachable")

    # Initialise
    init_chat_session()

    # Render
    render_chat_header()
    st.markdown("---")
    render_chat_messages()
    render_chat_input()


if __name__ == "__main__":
    main()
