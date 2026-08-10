"""Usage tracking API endpoint."""

import logging

from fastapi import APIRouter, Depends

from src.infrastructure.llm.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level tracker singleton (wired in app.py via dependency)
_tracker: TokenTracker | None = None


def set_tracker(tracker: TokenTracker) -> None:
    """Set the shared tracker instance (called during app wiring)."""
    global _tracker
    _tracker = tracker


def get_tracker() -> TokenTracker:
    global _tracker
    if _tracker is None:
        logger.warning(
            "No usage tracker was wired; fabricating a fresh TokenTracker. "
            "Check app wiring (create_app -> usage.set_tracker)."
        )
        _tracker = TokenTracker()
    return _tracker


@router.get("/api/usage")
async def get_usage(
    tracker: TokenTracker = Depends(get_tracker), limit: int = 10
) -> dict[str, object]:
    """Return LLM usage summary and recent records."""
    return {
        **tracker.get_summary(),
        "recent": tracker.get_recent(limit=min(max(limit, 1), 100)),
    }
