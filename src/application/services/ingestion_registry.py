"""In-process tracking for background document ingestion.

Ingestion is slow — parsing, embedding and storing a few hundred pages takes
minutes — so `POST /documents/upload` returns `202 Accepted` immediately and the
work continues on a background task. That leaves the frontend needing one
question answered: *is that document ready yet?* This module is the answer.

Deliberately in-memory rather than persisted:

  * the status is only meaningful while the process is running, and this app is
    a single local server — a restart clears it;
  * a document that finished ingesting is already visible in `/documents`, so
    the only thing lost on a restart is the progress bar for work that was in
    flight, not the document itself.

If this ever needs to survive a restart or serve more than one worker, the swap
is to back this with the same SQLite store the conversation history uses. The
surface the route depends on is three methods.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# How many finished jobs to remember. The list endpoint reads *live* status for
# anything still in flight, so this only bounds what `/status/{id}` can answer
# for a completed upload — long enough to cover a user navigating away and back.
_MAX_RETAINED = 200


class IngestionStatus(str, Enum):
    """Lifecycle of one ingestion job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class _Job:
    """Mutable record for one ingestion. Guarded by the registry's lock."""

    __slots__ = (
        "document_id",
        "filename",
        "status",
        "chunk_count",
        "error",
        "updated_at",
    )

    def __init__(self, document_id: str, filename: str) -> None:
        self.document_id = document_id
        self.filename = filename
        self.status = IngestionStatus.PENDING
        self.chunk_count = 0
        self.error: str | None = None
        self.updated_at = datetime.now(UTC)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "status": self.status.value,
            "chunk_count": self.chunk_count,
            "error": self.error,
            "updated_at": self.updated_at.isoformat(),
        }


class IngestionRegistry:
    """Thread-safe map of document id to ingestion progress."""

    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        # The ingestion task runs on a worker thread (the embedding model blocks),
        # so the registry can be written from outside the event loop.
        self._lock = threading.Lock()

    def start(self, document_id: str, filename: str) -> None:
        with self._lock:
            self._jobs[document_id] = _Job(document_id, filename)
            self._prune()

    def mark_processing(self, document_id: str) -> None:
        self._update(document_id, status=IngestionStatus.PROCESSING)

    def mark_complete(self, document_id: str, chunk_count: int) -> None:
        self._update(
            document_id, status=IngestionStatus.COMPLETE, chunk_count=chunk_count
        )

    def mark_failed(self, document_id: str, error: str) -> None:
        # Truncated: the detail is for a UI toast, and a parser traceback can run
        # to thousands of characters.
        self._update(document_id, status=IngestionStatus.FAILED, error=error[:300])

    def get(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(document_id)
            return job.as_dict() if job else None

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.as_dict() for job in self._jobs.values()]

    def _update(self, document_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(document_id)
            if job is None:
                # A job pruned or never registered. Creating it here would mask a
                # real wiring bug, so log loudly instead of silently succeeding.
                logger.warning(
                    "Ingestion update for unknown document_id=%s: %s",
                    document_id,
                    fields,
                )
                return
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(UTC)

    def _prune(self) -> None:
        """Drop the oldest finished jobs once the map grows past the cap."""
        if len(self._jobs) <= _MAX_RETAINED:
            return
        finished = [
            (job.updated_at, key)
            for key, job in self._jobs.items()
            if job.status in (IngestionStatus.COMPLETE, IngestionStatus.FAILED)
        ]
        # Oldest first; never evict one that is still running.
        for _, key in sorted(finished)[: len(self._jobs) - _MAX_RETAINED]:
            del self._jobs[key]


# Module-level singleton. The route owns it via a Registry like every other
# injected dependency, so tests can substitute their own instance.
registry = IngestionRegistry()
