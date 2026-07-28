"""ChatBubble — reusable component for rendering a single chat message."""

import streamlit as st


def render_sources(sources: list[dict], key_suffix: str = "") -> None:
    """Render source citations inside a collapsible expander.

    Parameters
    ----------
    sources:
        List of source dicts with ``content``, ``metadata``, and ``score`` keys.
    key_suffix:
        Unique string appended to widget keys to avoid collisions.
    """
    if not sources:
        return

    with st.expander(
        f"\U0001f4ce {len(sources)} source{'s' if len(sources) != 1 else ''}",
        expanded=False,
    ):
        for i, source in enumerate(sources, 1):
            content = source.get("content", "")
            metadata = source.get("metadata", {})
            score = source.get("score", 0.0)
            filename = metadata.get("filename", "unknown")

            st.markdown(f"**Source {i}** \u2014 *{filename}* (relevance: {score:.2f})")
            st.text(content[:500] + ("..." if len(content) > 500 else ""))
            if i < len(sources):
                st.markdown("---")


def render_message(message: dict, key_prefix: str = "msg") -> None:
    """Render a single chat bubble with optional source citations.

    Parameters
    ----------
    message:
        Dict with ``role`` and ``content`` keys; optionally ``sources``.
    key_prefix:
        Prefix for internal Streamlit widget keys.
    """
    role = message["role"]
    content = message["content"]

    with st.chat_message(role):
        st.markdown(content)
        if message.get("sources"):
            render_sources(message["sources"], key_suffix=key_prefix)
