"""Registry of RAG system-prompt versions.

Holds the versioned system-prompt templates used by the RAG engine and
resolves a version id to its template. ``v1`` is the original template
(byte-identical to the pre-versioning prompt); unknown versions fall back
to ``v1`` with a logged warning so a bad ``PROMPT_VERSION`` can never
break the pipeline.
"""

import logging

from src.infrastructure.config.settings import get_settings

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


class PromptRegistry:
    """Resolves prompt version ids to system-prompt templates.

    Args:
        default_version: Version used when no version is selected
            explicitly. Defaults to ``DEFAULT_PROMPT_VERSION``.
    """

    def __init__(self, default_version: str = DEFAULT_PROMPT_VERSION) -> None:
        self.default_version = default_version

    def get_prompt(self, version: str) -> str:
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


def create_prompt_registry(settings: object | None = None) -> PromptRegistry:
    """Create a PromptRegistry configured from application settings.

    Args:
        settings: Settings object to read ``PROMPT_VERSION`` from.
            Defaults to ``get_settings()``.

    Returns:
        A registry whose ``default_version`` mirrors the configured
        ``PROMPT_VERSION``; invalid or missing values fall back to
        ``"v1"``.
    """
    if settings is None:
        settings = get_settings()
    default_version = getattr(settings, "PROMPT_VERSION", DEFAULT_PROMPT_VERSION)
    if not isinstance(default_version, str) or not default_version:
        default_version = DEFAULT_PROMPT_VERSION
    return PromptRegistry(default_version=default_version)


__all__ = [
    "DEFAULT_PROMPT_VERSION",
    "PROMPT_VERSIONS",
    "PromptRegistry",
    "create_prompt_registry",
]
