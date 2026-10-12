"""Render an export bundle to plain text.

The fallback format: it has to survive being pasted into an email, a ticket, or
a notes app that has no idea what Markdown is. So there is no markup at all —
only a 78-column rule between turns to keep a long transcript readable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RULE = "=" * 78
THIN_RULE = "-" * 78


def _messages(conversation: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    messages = conversation.get("messages")
    if not isinstance(messages, list):
        return []
    return [m for m in messages if isinstance(m, Mapping)]


def _wrap(text: str, width: int = 78, indent: str = "") -> list[str]:
    """Greedy word wrap.

    Words longer than the line (a URL, a base64 blob) are not broken — splitting
    them would make the text harder to copy back out, and a long token is the
    one case where the reader needs it intact.
    """
    out: list[str] = []
    for paragraph in (text or "").splitlines() or [""]:
        if not paragraph.strip():
            out.append("")
            continue
        line = indent
        for word in paragraph.split():
            candidate = word if line == indent else f"{line} {word}"
            if len(candidate) > width and line != indent:
                out.append(line)
                line = indent + word
            else:
                line = candidate
        out.append(line)
    return out


def render_text(export: Mapping[str, Any]) -> str:
    """Render the whole export bundle as a plain-text document."""
    lines: list[str] = [
        RULE,
        "MARGINALIA EXPORT",
        RULE,
        f"Exported:     {export.get('exported_at', '')}",
        f"App version:  {export.get('app_version', '')}",
        f"Documents:    {len(export.get('documents') or [])}",
        "",
    ]

    documents = export.get("documents") or []
    if documents:
        lines += ["DOCUMENTS", THIN_RULE]
        for doc in documents:
            if not isinstance(doc, Mapping):
                continue
            lines.append(
                f"- {doc.get('filename', '')}"
                f"  [{doc.get('content_type', '')},"
                f" {doc.get('chunk_count', 0)} chunks,"
                f" {doc.get('file_size', 0)} bytes]"
            )
        lines.append("")

    conversations = export.get("conversations") or []
    if not conversations:
        lines += ["No conversations saved yet.", ""]

    for conversation in conversations:
        if not isinstance(conversation, Mapping):
            continue
        lines += [
            RULE,
            str(conversation.get("title", "Untitled")).upper(),
            RULE,
            f"{conversation.get('created_at', '')}"
            f"  ->  {conversation.get('updated_at', '')}",
            "",
        ]
        for message in _messages(conversation):
            who = (
                "YOU" if str(message.get("role", "")).lower() == "user" else "ASSISTANT"
            )
            lines += [f"[{who}] {message.get('created_at', '')}", THIN_RULE]
            lines += _wrap(str(message.get("content", "")))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
