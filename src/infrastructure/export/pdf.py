"""Render an export bundle to a PDF, without a PDF library.

Why not reportlab or fpdf2: this app is a local-first tool whose whole point is
`pip install -e .` and run. Both of those pull Pillow, adding tens of megabytes
to a transcript exporter — for output that is plain text on white paper. So this
module emits the smallest thing that is still a valid PDF: one of the base-14
fonts (Courier, which ships with every reader and needs no embedding) and a text
content stream per page.

The trade-off is explicit. This handles text only — no images, no fonts, no
tables beyond what is already drawn as characters. If the export ever needs
richer output, `render_pdf` is the only function to replace; the route and the
other renderers do not change.

Courier is monospaced at 0.6em, so at 10pt every character is exactly 6pt wide.
That makes the column count arithmetic exact rather than a guess, which is what
lets the wrap below match the PDF's own text operators.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any

PAGE_WIDTH = 595  # A4, in points (72 per inch).
PAGE_HEIGHT = 842
MARGIN = 56
FONT_SIZE = 10
LEADING = 12
# Courier is 0.6 * FONT_SIZE per glyph.
CHAR_WIDTH = FONT_SIZE * 0.6
COLUMNS = int((PAGE_WIDTH - 2 * MARGIN) / CHAR_WIDTH)  # 80
LINES_PER_PAGE = int((PAGE_HEIGHT - 2 * MARGIN) / LEADING)  # 60
FIRST_BASELINE = PAGE_HEIGHT - MARGIN

# PDF's WinAnsi encoding has no room for typographic punctuation or maths, and
# this is a transcript a reader will copy text out of. Folding to ASCII up front
# is more honest than letting a replacement character leak into the file.
#
# The maths entries are here because the corpus this app is pointed at is full of
# formulae — an unexplained `?` where a phi should be reads like a broken export,
# and transliterating to "phi" is far better than either "?" or a wrong glyph.
_ASCII_FOLD = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "→": "->",
    " ": " ",
    "•": "*",
    "·": "*",
    # Greek — the ones that actually appear in formulae, spelled out.
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "θ": "theta",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "τ": "tau",
    "φ": "phi",
    "ω": "omega",
    "Δ": "Delta",
    "Σ": "Sigma",
    "Ω": "Omega",
    # Operators and symbols
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "≈": "~",
    "≡": "==",
    "×": "x",
    "÷": "/",
    "∞": "inf",
    "√": "sqrt",
    "∑": "sum",
    "∏": "prod",
    "∫": "int",
    "∈": " in ",
    "∉": " not in ",
    "⊂": "subset",
    "∪": "U",
    "∩": "intersect",
    "°": "deg",
    "±": "+/-",
    "−": "-",  # minus sign, distinct from a hyphen
    # Unicode has a second Greek block used for maths: ϕ U+03D5 is not φ
    # U+03C6, and ϑ is not θ. A maths-heavy corpus uses both, and mapping only
    # the letterform the font happens to favour turns half of them into `?`.
    "ϕ": "phi",
    "ϑ": "theta",
    "ϖ": "pi",
    "ϵ": "epsilon",
    "ϱ": "rho",
    "⁄": "/",  # fraction slash, what NFKD produces for ½
}


def _to_ascii(text: str) -> str:
    table = str.maketrans(_ASCII_FOLD)

    # The fold runs on BOTH sides of the NFKD pass, because each needs it for a
    # different reason.
    #   before — NFKD splits ≠ into "=" plus a combining slash, so the map has to
    #            claim the character before that happens or the combining mark
    #            survives and lands as "?".
    #   after  — NFKD turns ½ into "1⁄2", and the fraction slash it introduces
    #            only exists once the decomposition has run.
    folded = (text or "").translate(table)
    decomposed = unicodedata.normalize("NFKD", folded).translate(table)

    # Drop any combining marks left over from that decomposition — they have no
    # Latin-1 representation and would otherwise land as replacement glyphs.
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    # Anything still outside Latin-1 becomes a space rather than a replacement
    # glyph, so a stray emoji cannot corrupt the encoding.
    return stripped.encode("latin-1", "replace").decode("latin-1")


def _escape(text: str) -> str:
    """Fold to Latin-1, then escape what is structural inside a PDF string.

    Folding happens here rather than in the caller so no drawn text can reach
    the encoder un-folded — `encode("latin-1", "replace")` would otherwise turn
    an em dash into a `?` and silently lose it.
    """
    return _to_ascii(text).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str, width: int = COLUMNS) -> list[str]:
    """Greedy word wrap, same contract as the plain-text renderer."""
    out: list[str] = []
    for paragraph in (text or "").splitlines() or [""]:
        if not paragraph.strip():
            out.append("")
            continue
        line = ""
        for word in paragraph.split():
            candidate = word if not line else f"{line} {word}"
            if len(candidate) > width and line:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return out


def _content_stream(page_lines: list[str]) -> bytes:
    """Build the content stream that draws one page of text.

    `Tm` sets the text matrix once at the top-left of the text block; every
    following line is `Tj` (show text) followed by `T*` (next line), which moves
    down by the leading set with `TL`. Emitting absolute coordinates per line
    instead would be simpler to read but bloats the stream for no benefit.
    """
    parts = [
        "BT",
        f"/F1 {FONT_SIZE} Tf",
        f"{LEADING} TL",
        f"1 0 0 1 {MARGIN} {FIRST_BASELINE} Tm",
    ]
    parts += [f"({_escape(line)}) Tj T*" for line in page_lines]
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", "replace")


def _paginate(lines: list[str]) -> list[list[str]]:
    """Split the flat line list into pages, never leaving one page empty."""
    if not lines:
        return [[]]
    return [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]


def _document_lines(export: Mapping[str, Any]) -> list[str]:
    """Flatten the export bundle into the text that goes in the PDF."""
    out: list[str] = [
        "MARGINALIA EXPORT",
        "=" * COLUMNS,
        f"Exported:    {export.get('exported_at', '')}",
        f"App version: {export.get('app_version', '')}",
        f"Documents:   {len(export.get('documents') or [])}",
        "",
    ]

    documents = export.get("documents") or []
    if documents:
        out += ["DOCUMENTS", "-" * COLUMNS]
        for doc in documents:
            if not isinstance(doc, Mapping):
                continue
            out += _wrap(
                f"- {doc.get('filename', '')}  [{doc.get('content_type', '')},"
                f" {doc.get('chunk_count', 0)} chunks, {doc.get('file_size', 0)} bytes]"
            )
        out.append("")

    conversations = export.get("conversations") or []
    if not conversations:
        out += ["No conversations saved yet.", ""]

    for conversation in conversations:
        if not isinstance(conversation, Mapping):
            continue
        out += [
            "",
            "=" * COLUMNS,
            str(conversation.get("title", "Untitled")).upper(),
            "=" * COLUMNS,
            "",
        ]
        messages = conversation.get("messages")
        for message in messages if isinstance(messages, list) else []:
            if not isinstance(message, Mapping):
                continue
            who = (
                "YOU" if str(message.get("role", "")).lower() == "user" else "ASSISTANT"
            )
            out += [f"[{who}]", "-" * COLUMNS]
            out += _wrap(str(message.get("content", "")))
            out.append("")

    return out


def _assemble(objects: list[bytes]) -> bytes:
    """Concatenate objects into a PDF file with a correct cross-reference table.

    The xref offsets have to be byte-exact, which is why the body is built as
    bytes and measured as it goes. Every entry is written as a fixed 20 bytes,
    as the spec requires, so a reader can seek directly to object N.
    """
    out = bytearray(
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    )  # binary marker: stops tools mangling the file
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"  # object 0 is always the free head
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
    out += f"startxref\n{xref_at}\n%%EOF\n".encode("ascii")
    return bytes(out)


def render_pdf(export: Mapping[str, Any]) -> bytes:
    """Render the whole export bundle as a PDF document."""
    pages = _paginate(_document_lines(export))

    # Object numbering is fixed so /Root and /Kids can be written before the
    # objects they point at exist: 1 catalog, 2 page tree, 3 font, then
    # (content, page) pairs from 4 upwards.
    font_obj = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier "
        b"/Encoding /WinAnsiEncoding >>"
    )
    page_objects: list[bytes] = []
    content_objects: list[bytes] = []

    for page_lines in pages:
        stream = _content_stream(page_lines)
        content_objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        page_objects.append(b"")  # placeholder, filled once numbering is known

    first_page = 4
    kids = " ".join(f"{first_page + 2 * i + 1} 0 R" for i in range(len(pages)))
    for i in range(len(pages)):
        content_no = first_page + 2 * i
        page_objects[i] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_no} 0 R >>"
        ).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        font_obj,
    ]
    for i in range(len(pages)):
        objects.append(content_objects[i])
        objects.append(page_objects[i])

    return _assemble(objects)


def suggested_filename(export: Mapping[str, Any], extension: str) -> str:
    """Build the download filename, stamped with the export time."""
    stamp = (
        str(export.get("exported_at", ""))
        .replace(":", "")
        .replace("-", "")
        .replace("T", "-")
    )
    stamp = stamp.split(".")[0].strip("-") or "export"
    return f"marginalia-export-{stamp}.{extension}"
