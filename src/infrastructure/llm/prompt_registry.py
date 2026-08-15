"""Versioned RAG system-prompt templates.

Holds the versioned system-prompt templates used by the RAG engine.
``v1`` is the original template (byte-identical to the pre-versioning
prompt); unknown versions fall back to ``v1`` with a logged warning so a
bad ``PROMPT_VERSION`` can never break the pipeline.
"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_VERSION = "v1"

PROMPT_VERSIONS: dict[str, str] = {
    "v1": (
        "You are a helpful assistant that answers questions "
        "based on the provided context.\n\n"
        "Context from documents:\n{context}\n\n"
        "Question: {question}\n\n"
        "Instructions:\n"
        "- Answer the question based on the context provided\n"
        "- If the context doesn't contain enough information, "
        "say so clearly\n"
        "- Cite your sources when possible by referencing the "
        "document names\n"
        "- Be concise and accurate\n"
        "- If multiple sources provide different information, "
        "mention both perspectives"
    ),
    # Groundedness-focused variant: stricter about staying within the
    # provided context and admitting when the answer is not present.
    "v2": (
        "You are a helpful assistant that answers questions "
        "based on the provided context.\n\n"
        "Context from documents:\n{context}\n\n"
        "Question: {question}\n\n"
        "Instructions:\n"
        "- Answer using only the provided context; never rely on "
        "outside knowledge\n"
        "- If the context does not contain the answer, say so "
        "clearly instead of guessing\n"
        "- Cite your sources by referencing the document names "
        "for every claim you make\n"
        "- Be concise and accurate\n"
        "- If multiple sources provide different information, "
        "mention both perspectives\n"
        "- Do not invent facts, figures, or sources that are not "
        "present in the context"
    ),
}


def get_prompt(version: str) -> str:
    """Return the system-prompt template for ``version``.

    Args:
        version: Prompt version id (e.g. ``"v1"``, ``"v2"``).

    Returns:
        The template text. Unknown versions fall back to the v1
        template (the original) with a logged warning.
    """
    template = PROMPT_VERSIONS.get(version)
    if template is None:
        logger.warning(
            "Unknown prompt version %r; falling back to %r",
            version,
            DEFAULT_PROMPT_VERSION,
        )
        return PROMPT_VERSIONS[DEFAULT_PROMPT_VERSION]
    return template


__all__ = [
    "DEFAULT_PROMPT_VERSION",
    "PROMPT_VERSIONS",
    "get_prompt",
]
