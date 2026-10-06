"""Resolves the active LLM API key from the user store, falling back to env.

The precedence is deliberate: an explicit key typed into the Settings page wins
over ``.env``, because the user just told us which credential to use. Clearing
the stored key falls back to the environment value rather than leaving the app
with no credential at all.
"""

import logging

from src.domain.interfaces.secret_store import SecretStore
from src.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

# Where the active key came from, surfaced in the UI so the source is never a
# mystery. "none" means neither store nor env has a key.
SOURCE_USER = "user"
SOURCE_ENV = "env"
SOURCE_NONE = "none"


class ApiKeyResolver:
    """Single point of truth for "which API key should we use right now?".

    Args:
        store: Holds the user-supplied key.
        settings: Supplies the environment fallback.
    """

    def __init__(self, store: SecretStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    def resolve(self) -> str:
        """Return the active key, or ``""`` when nothing is configured."""
        stored = self._store.get_api_key()
        if stored:
            return stored
        return self._settings.GEMINI_API_KEY or ""

    def source(self) -> str:
        """Return which store the active key came from."""
        if self._store.get_api_key():
            return SOURCE_USER
        if self._settings.GEMINI_API_KEY:
            return SOURCE_ENV
        return SOURCE_NONE


def mask_api_key(api_key: str | None) -> str | None:
    """Return a display-safe rendering, never the key itself.

    Only the last four characters survive, which is enough for a user to tell
    two keys apart without the response becoming a credential leak.
    """
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return f"{'*' * 8}{api_key[-4:]}"
