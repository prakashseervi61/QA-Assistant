"""Render an export bundle to Markdown.

Plain string building rather than a template engine: the output is a transcript,
so the only things that need escaping are the two characters Markdown treats as
structure inside a paragraph. Escaping those in the body is what stops a pasted
answer containing ``#`` or ``*`` from rewriting the shape of the export.

Answers go in blockquotes rather than under a heading, because the citation
chips that follow an answer are the part a reader needs to see next to it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Only these two are structural inside a paragraph of body text. `#` only leads
# a heading at the start of a line and `-` only makes a list when the line
# starts with it, so escaping them everywhere would litter the output.
_MD_SPECIALS = str.maketrans({ord("\\"): "\\\\", ord("`"): "\\`"})


def escape(text: str) -> str:
    """Escape the Markdown metacharacters that can appear mid-paragraph."""
    return (text or "").translate(_MD_SPECIALS)


def _messages(conversation: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    messages = conversation.get("messages")
    return messages if isinstance(messages, list) else []


def _sources(message: Mapping[str, Any]) -> str:
    """Render the citation chips as a single `Sources:` line.

    Only the filename is kept: the export is a reading copy, and the page/percent
    that the live UI shows is meaningless once the document is out of the app.
    """
    names: list[str] = []
    for source in message.get("sources") or []:
        if isinstance(source, Mapping):
            meta = source.get("metadata")
            name = meta.get("filename") if isinstance(meta, Mapping) else None
        else:
            name = None
        if name and name not in names:
            names.append(str(name))
    return ", ".join(names)


def render_markdown(export: Mapping[str, Any]) -> str:
    """Render the whole export bundle as a Markdown document."""
    lines: list[str] = [
        "# Marginalia export",
        "",
        f"- Exported: {export.get('exported_at', '')}",
        f"- App version: {export.get('app_version', '')}",
        f"- Documents: {len(export.get('documents') or [])}",
        "",
    ]

    documents = export.get("documents") or []
    if documents:
        lines += [
            "## Documents",
            "",
            "| File | Type | Chunks | Size | Added |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for doc in documents:
            if not isinstance(doc, Mapping):
                continue
            lines.append(
                "| {name} | {kind} | {chunks} | {size} | {added} |".format(
                    name=escape(str(doc.get("filename", ""))),
                    kind=escape(str(doc.get("content_type", ""))),
                    chunks=doc.get("chunk_count", 0),
                    size=_human_size(doc.get("file_size", 0)),
                    added=doc.get("created_at", ""),
                )
            )
        lines.append("")

    conversations = export.get("conversations") or []
    if not conversations:
        lines += ["_No conversations saved yet._", ""]

    for conversation in conversations:
        if not isinstance(conversation, Mapping):
            continue
        lines += [
            "---",
            "",
            f"## {escape(str(conversation.get('title', 'Untitled')))}",
            "",
        ]

        for message in _messages(conversation):
            if not isinstance(message, Mapping):
                continue
            role = str(message.get("role", "")).lower()
            content = str(message.get("content", ""))

            if role == "user":
                lines += [
                    f"**You** · {message.get('created_at', '')}",
                    "",
                    escape(content),
                    "",
                ]
            else:
                lines += [f"**Assistant** · {message.get('created_at', '')}", ""]
                # Blockquote keeps the answer visually separate from the prompt,
                # which matters once several turns stack up.
                #
                # The answer is escaped for the same reason the question is: it
                # came from a model, so it can contain a line starting with `#`
                # or a stray backslash, and unescaped that injects structure
                # into the exported document.
                lines += [
                    f"> {escape(line)}" if line else ">"
                    for line in content.splitlines()
                ]
                lines.append("")
                sources = _sources(message)
                if sources:
                    lines += [f"**Sources:** {escape(sources)}", ""]

    return "\n".join(lines).rstrip() + "\n"


def _human_size(num_bytes: object) -> str:
    """Render a byte count as a short human string for the table cell."""
    try:
        size = float(num_bytes)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "—"
