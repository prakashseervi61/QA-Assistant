"""Guardrail check primitives: PII detection, prompt-injection detection,
and a groundedness (hallucination) heuristic.

All functions are pure, synchronous, and dependency-free (stdlib ``re``
only). They are designed to never raise for well-formed string inputs.
"""

import re

# ---------------------------------------------------------------------------
# PII detection
# ---------------------------------------------------------------------------

#: Regex patterns per PII type. Keys are stable identifiers surfaced in
#: guardrail metadata; values are compiled at call time.
PII_PATTERNS: dict[str, str] = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}


def detect_pii(text: str) -> list[dict[str, object]]:
    """Detect PII (email, phone, SSN, credit card, IP) in ``text``.

    Args:
        text: The text to scan.

    Returns:
        A list of ``{"type": str, "match": str}`` dicts, one per hit.
        Empty when no PII is found.
    """
    issues: list[dict[str, object]] = []
    for pii_type, pattern in PII_PATTERNS.items():
        for match in re.finditer(pattern, text):
            issues.append({"type": pii_type, "match": match.group(0)})
    return issues


def redact_pii(text: str) -> str:
    """Replace all PII matches in ``text`` with ``[REDACTED]``.

    Args:
        text: The text to redact.

    Returns:
        The redacted text.
    """
    redacted = text
    for pattern in PII_PATTERNS.values():
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted


# ---------------------------------------------------------------------------
# Prompt-injection detection
# ---------------------------------------------------------------------------

#: Case-insensitive regex fragments that commonly indicate prompt injection.
INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(?:all\s+)?previous\s+(?:instructions?|prompts?|messages?)",
    r"disregard\s+(?:all\s+)?previous\s+(?:instructions?|prompts?|messages?)",
    r"you\s+are\s+now\b",
    r"system\s+prompt",
    r"act\s+as\b",
    r"forget\s+everything",
    r"reveal\s+(?:your\s+)?(?:system\s+)?prompt",
    r"jailbreak",
    r"bypass\s+(?:your\s+)?(?:safety|restrictions?|rules?)",
    r"do\s+(?:anything|whatever)\s+you\s+want",
    r"override\s+(?:your|previous|all)\s+(?:instructions?|prompts?)",
    r"new\s+instructions?",
]


def detect_prompt_injection(text: str) -> list[dict[str, object]]:
    """Detect prompt-injection patterns in ``text``.

    Args:
        text: The text to scan.

    Returns:
        A list of ``{"type": "prompt_injection", "match": str}`` dicts.
        Empty when no patterns match.
    """
    issues: list[dict[str, object]] = []
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, lowered)
        if match is not None:
            issues.append({"type": "prompt_injection", "match": match.group(0)})
    return issues


# ---------------------------------------------------------------------------
# Groundedness (hallucination) heuristic
# ---------------------------------------------------------------------------

#: Common English stop words excluded from groundedness word counts.
STOPWORDS: set[str] = {
    "the",
    "and",
    "for",
    "are",
    "but",
    "not",
    "you",
    "all",
    "any",
    "can",
    "her",
    "was",
    "one",
    "our",
    "out",
    "get",
    "has",
    "him",
    "his",
    "how",
    "new",
    "now",
    "old",
    "see",
    "two",
    "way",
    "who",
    "did",
    "its",
    "let",
    "put",
    "say",
    "she",
    "too",
    "use",
    "that",
    "with",
    "have",
    "this",
    "will",
    "your",
    "from",
    "they",
    "know",
    "want",
    "been",
    "good",
    "much",
    "some",
    "time",
    "very",
    "when",
    "come",
    "here",
    "just",
    "like",
    "long",
    "make",
    "many",
    "more",
    "only",
    "over",
    "such",
    "take",
    "than",
    "them",
    "well",
    "were",
    "what",
    "which",
    "while",
    "would",
    "there",
    "their",
}


def compute_groundedness(answer: str, contexts: list[str]) -> float:
    """Compute a groundedness score for ``answer`` against ``contexts``.

    The score is the fraction of answer content words (length > 3 and not a
    stop word) that appear in the concatenated retrieved contexts.
    Returns 0.0 when there is no context to verify against or the answer
    contains no extractable words, and 1.0 when the answer carries words
    but no content words to check.

    Args:
        answer:   The generated answer text.
        contexts: Concatenated retrieved context strings.

    Returns:
        Groundedness in ``[0.0, 1.0]``.
    """
    if not contexts:
        return 0.0

    words = re.findall(r"[a-z]+", answer.lower())
    if not words:
        return 0.0

    content_words = [w for w in words if len(w) > 3 and w not in STOPWORDS]
    if not content_words:
        return 1.0

    context_text = " ".join(contexts).lower()
    found = sum(1 for w in content_words if w in context_text)
    return found / len(content_words)
