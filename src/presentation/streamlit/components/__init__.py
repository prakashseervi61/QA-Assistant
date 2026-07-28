"""Shared Streamlit UI components."""

import streamlit as st


def render_sources(sources: list[dict], key_suffix: str = "") -> None:
    """Render source citations inside a collapsible expander."""
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
