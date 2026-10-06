"""JSON-file implementation of :class:`SecretStore`.

A plain local file rather than a database row: there is exactly one secret, it
is written rarely, and a human-readable file is easier to audit or hand-edit
than a table. The security posture deliberately matches ``.env`` — the key is
already on disk in plaintext there, so this neither improves nor worsens it.
The API is loopback-only; that boundary is the access control.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from src.domain.interfaces.secret_store import SecretStore

logger = logging.getLogger(__name__)


class JsonSecretStore(SecretStore):
    """Stores the user-supplied API key in a single-key JSON file.

    Args:
        path: File to read and write. Parent directories are created on write.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def get_api_key(self) -> str | None:
        """Return the stored key, or ``None`` when absent or unreadable.

        A corrupt file is treated as "no key stored" rather than raising: the
        user can still fall back to the environment key, and a settings file
        should never be able to stop the app from starting.
        """
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            logger.warning("Could not read secrets file %s", self._path, exc_info=True)
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Secrets file %s is not valid JSON; ignoring it", self._path)
            return None

        key = data.get("gemini_api_key")
        if not isinstance(key, str) or not key.strip():
            return None
        return key

    def set_api_key(self, api_key: str) -> None:
        """Write the key atomically so a crash cannot truncate the file."""
        payload = json.dumps({"gemini_api_key": api_key}, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temp file in the same directory, then rename: rename is
        # atomic within a filesystem, so a reader never sees a half-written file.
        handle, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".secrets-", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(payload)
            # Owner-only where the platform supports it (a no-op on Windows).
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def clear_api_key(self) -> None:
        """Delete the file. Clearing an already-empty store is not an error."""
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning(
                "Could not remove secrets file %s", self._path, exc_info=True
            )
