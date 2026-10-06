"""Port for runtime-managed secrets (currently the Gemini API key)."""

from abc import ABC, abstractmethod


class SecretStore(ABC):
    """Persists credentials that a user supplies through the UI.

    Separate from ``Settings`` on purpose: settings come from the environment
    at startup and are read-only, whereas these are written at runtime by the
    user. Keeping them apart means a user-supplied key can never be confused
    with configuration, and the environment stays the fallback default.
    """

    @abstractmethod
    def get_api_key(self) -> str | None:
        """Return the user-supplied API key, or ``None`` if none is stored."""
        ...

    @abstractmethod
    def set_api_key(self, api_key: str) -> None:
        """Persist the user-supplied API key, replacing any previous one."""
        ...

    @abstractmethod
    def clear_api_key(self) -> None:
        """Remove the stored key, falling back to the environment value."""
        ...
