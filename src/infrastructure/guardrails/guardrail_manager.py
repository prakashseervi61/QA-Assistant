"""GuardrailManager: orchestrates input (PII + prompt injection) and output
(groundedness + PII leak) checks around the RAG pipeline.

The manager is feature-flagged: when constructed with ``enable=False`` every
check passes through untouched. The engine integration is fully optional —
when no manager is wired in, the pipeline behaves exactly as before.
"""

import logging

from src.infrastructure.config.settings import get_settings
from src.infrastructure.guardrails.checks import (
    compute_groundedness,
    detect_pii,
    detect_prompt_injection,
)

logger = logging.getLogger(__name__)

#: Answer returned to the user when an input guardrail blocks a query.
BLOCKED_MESSAGE = "Your request was blocked by safety filters."


class GuardrailManager:
    """Runs guardrail checks for the RAG pipeline.

    Args:
        enable:              Master switch — when False all checks pass.
        block_violations:    When True, flagged inputs are blocked (the
                             query is not sent to the LLM). When False,
                             violations are flagged but never blocked.
        groundedness_threshold: Minimum groundedness score below which the
                             output is flagged.
    """

    def __init__(
        self,
        enable: bool,
        block_violations: bool,
        groundedness_threshold: float = 0.2,
    ) -> None:
        self._enable = enable
        self._block_violations = block_violations
        self._groundedness_threshold = groundedness_threshold

    # ------------------------------------------------------------------
    # Input checks (pre-retrieval)
    # ------------------------------------------------------------------

    def check_input(self, text: str) -> dict[str, object]:
        """Check the user question for PII and prompt injection.

        Args:
            text: The user question.

        Returns:
            ``{"flagged": bool, "issues": list, "blocked": bool}``.
            When disabled: ``{"flagged": False, "issues": [], "blocked": False}``.
        """
        if not self._enable:
            return {"flagged": False, "issues": [], "blocked": False}

        issues: list[dict[str, object]] = []
        issues.extend(detect_pii(text))
        issues.extend(detect_prompt_injection(text))

        flagged = len(issues) > 0
        blocked = flagged and self._block_violations
        if flagged:
            logger.info(
                "Input guardrail flagged %d issue(s); blocked=%s", len(issues), blocked
            )
        return {
            "flagged": flagged,
            "issues": issues,
            "blocked": blocked,
        }

    # ------------------------------------------------------------------
    # Output checks (post-generation)
    # ------------------------------------------------------------------

    def check_output(
        self, answer: str, contexts: list[str]
    ) -> dict[str, object]:
        """Check the generated answer for groundedness and PII leaks.

        Args:
            answer:   The generated answer text.
            contexts: Retrieved chunk contents used as grounding context.

        Returns:
            ``{"flagged": bool, "issues": list, "groundedness": float}``.
            When disabled: ``{"flagged": False, "issues": [],
            "groundedness": 1.0}``.
        """
        if not self._enable:
            return {"flagged": False, "issues": [], "groundedness": 1.0}

        groundedness = round(compute_groundedness(answer, contexts), 4)
        issues: list[dict[str, object]] = detect_pii(answer)
        if groundedness < self._groundedness_threshold:
            issues.append(
                {
                    "type": "low_groundedness",
                    "groundedness": groundedness,
                    "threshold": self._groundedness_threshold,
                }
            )

        flagged = len(issues) > 0
        if flagged:
            logger.info(
                "Output guardrail flagged %d issue(s); groundedness=%s",
                len(issues),
                groundedness,
            )
        return {
            "flagged": flagged,
            "issues": issues,
            "groundedness": groundedness,
        }


def create_guardrail_manager() -> GuardrailManager | None:
    """Create a guardrail manager from application settings.

    Returns None when ``ENABLE_GUARDRAILS`` is False (the default), so the
    RAG engine runs with zero behavior change.

    Returns:
        A configured :class:`GuardrailManager`, or None when disabled.
    """
    settings = get_settings()
    if not getattr(settings, "ENABLE_GUARDRAILS", False):
        return None
    return GuardrailManager(
        enable=True,
        block_violations=getattr(settings, "GUARDRAIL_BLOCK_VIOLATIONS", False),
        groundedness_threshold=getattr(
            settings, "GUARDRAIL_GROUNDEDNESS_THRESHOLD", 0.2
        ),
    )
