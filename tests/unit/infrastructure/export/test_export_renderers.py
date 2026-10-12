"""Tests for the export renderers.

The PDF tests go past "it returned some bytes": a PDF is only usable if a reader
can follow its cross-reference table, and a wrong byte offset produces a file
that looks fine and fails to open. So the assertions parse the xref table and
check every offset actually lands on the object it claims to — which is the only
part of the format that a hand-rolled writer gets wrong in ways no smoke test
would notice.
"""

from __future__ import annotations

import re

import pytest

from src.infrastructure.export import render_markdown, render_pdf, render_text
from src.infrastructure.export.pdf import (
    COLUMNS,
    LINES_PER_PAGE,
    _document_lines,
    _to_ascii,
    suggested_filename,
)


def bundle(**overrides):
    """A minimal but representative export payload."""
    base = {
        "exported_at": "2026-10-06T12:00:00+00:00",
        "app_version": "0.1.0",
        "documents": [
            {
                "id": "d1",
                "filename": "notes.pdf",
                "content_type": ".pdf",
                "file_size": 2048,
                "chunk_count": 12,
                "created_at": "2026-10-01",
            }
        ],
        "conversations": [
            {
                "id": "c1",
                "title": "What is RSA?",
                "created_at": "2026-10-05T10:00:00",
                "updated_at": "2026-10-05T10:01:00",
                "messages": [
                    {
                        "id": "m1",
                        "role": "user",
                        "content": "Explain RSA",
                        "created_at": "2026-10-05T10:00:00",
                        "sources": [],
                    },
                    {
                        "id": "m2",
                        "role": "assistant",
                        "content": "RSA is an asymmetric cipher.",
                        "created_at": "2026-10-05T10:00:30",
                        "sources": [
                            {"metadata": {"filename": "notes.pdf"}},
                            {"metadata": {"filename": "notes.pdf"}},
                        ],
                    },
                ],
            }
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


class TestMarkdown:
    def test_includes_documents_and_conversations(self):
        out = render_markdown(bundle())
        assert "# Marginalia export" in out
        assert "notes.pdf" in out
        assert "What is RSA?" in out
        assert "RSA is an asymmetric cipher." in out

    def test_escapes_markdown_metacharacters_in_content(self):
        """A pasted answer must not be able to inject structure.

        Without escaping, an answer containing a backtick would break the
        surrounding span and an answer containing a backslash would escape the
        next character out of the document.
        """
        out = render_markdown(
            bundle(
                conversations=[
                    {
                        "title": "t",
                        "created_at": "",
                        "updated_at": "",
                        "messages": [
                            {
                                "role": "assistant",
                                "content": "back`tick and back\\slash",
                                "created_at": "",
                                "sources": [],
                            }
                        ],
                    }
                ]
            )
        )
        assert r"back\`tick" in out
        assert r"back\\slash" in out

    def test_deduplicates_cited_sources(self):
        """The same file cited twice is one source, not two."""
        out = render_markdown(bundle())
        source_lines = [
            line for line in out.splitlines() if line.startswith("**Sources:**")
        ]
        assert len(source_lines) == 1
        assert source_lines[0].count("notes.pdf") == 1

    def test_survives_an_empty_bundle(self):
        out = render_markdown(
            {"exported_at": "", "app_version": "", "documents": [], "conversations": []}
        )
        assert "# Marginalia export" in out
        assert "No conversations" in out

    def test_ignores_malformed_rows_instead_of_raising(self):
        """A half-written conversation must not take the whole export down."""
        out = render_markdown(
            bundle(
                documents=["not-a-mapping"],
                conversations=[
                    {"title": "x", "messages": ["not-a-mapping", None]},
                    None,
                ],
            )
        )
        assert "Marginalia export" in out


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


class TestPlainText:
    def test_labels_each_turn(self):
        out = render_text(bundle())
        assert "[YOU]" in out
        assert "[ASSISTANT]" in out

    def test_wraps_at_the_column_limit(self):
        out = render_text(
            bundle(
                conversations=[
                    {
                        "title": "t",
                        "created_at": "",
                        "updated_at": "",
                        "messages": [
                            {
                                "role": "user",
                                "content": "word " * 200,
                                "created_at": "",
                                "sources": [],
                            }
                        ],
                    }
                ]
            )
        )
        body = [line for line in out.splitlines() if line.startswith("word")]
        assert body, "expected wrapped body lines"
        assert max(len(line) for line in body) <= 78

    def test_does_not_break_an_over_long_token(self):
        """Splitting a URL or key would make the text unusable to copy back."""
        token = "https://example.com/" + "a" * 200
        out = render_text(
            bundle(
                conversations=[
                    {
                        "title": "t",
                        "created_at": "",
                        "updated_at": "",
                        "messages": [
                            {
                                "role": "user",
                                "content": token,
                                "created_at": "",
                                "sources": [],
                            }
                        ],
                    }
                ]
            )
        )
        assert token in out

    def test_survives_an_empty_bundle(self):
        out = render_text(
            {"exported_at": "", "app_version": "", "documents": [], "conversations": []}
        )
        assert "MARGINALIA EXPORT" in out


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def parse_xref(pdf: bytes):
    """Return (xref_offset, entry_count, entries) from the cross-reference table."""
    match = re.search(rb"startxref\s+(\d+)\s+%%EOF", pdf)
    assert match, "missing startxref"
    at = int(match.group(1))
    assert pdf[at : at + 4] == b"xref", "startxref does not point at the xref table"
    rows = pdf[at:].split(b"\n")
    count = int(rows[1].split()[1])
    return at, count, rows[2 : 2 + count]


class TestPdfStructure:
    def test_has_the_required_envelope(self):
        pdf = render_pdf(bundle())
        assert pdf.startswith(b"%PDF-1.4")
        assert pdf.rstrip().endswith(b"%%EOF")

    def test_every_xref_offset_lands_on_its_object(self):
        """The failure mode a byte-writer actually has.

        A wrong offset yields a file that still ends in %%EOF and still parses
        as bytes, so the only way to know it is sound is to follow the table.
        """
        pdf = render_pdf(bundle())
        _, count, entries = parse_xref(pdf)
        assert entries[0].startswith(b"0000000000 65535 f"), (
            "object 0 must be the free head"
        )
        for number, entry in enumerate(entries[1:], start=1):
            assert len(entry) + 1 == 20, "xref entry must be 20 bytes with its newline"
            offset = int(entry.split()[0])
            expected = b"%d 0 obj" % number
            assert pdf[offset : offset + len(expected)] == expected

    def test_trailer_size_matches_the_table(self):
        pdf = render_pdf(bundle())
        _, count, _ = parse_xref(pdf)
        assert int(re.search(rb"/Size (\d+)", pdf).group(1)) == count

    def test_declared_stream_length_matches_the_bytes(self):
        pdf = render_pdf(bundle())
        for match in re.finditer(
            rb"<< /Length (\d+) >>\nstream\n(.*?)\nendstream", pdf, re.S
        ):
            assert int(match.group(1)) == len(match.group(2))

    def test_page_tree_matches_the_pages_it_lists(self):
        pdf = render_pdf(bundle())
        kids = re.findall(rb"(\d+) 0 R", re.search(rb"/Kids \[(.*?)\]", pdf).group(1))
        assert int(re.search(rb"/Count (\d+)", pdf).group(1)) == len(kids)
        for kid in kids:
            assert re.search(rb"%s 0 obj\n<< /Type /Page " % kid, pdf), (
                "kid must be a page"
            )

    def test_catalog_points_at_the_page_tree(self):
        pdf = render_pdf(bundle())
        assert b"/Type /Catalog /Pages 2 0 R" in pdf
        assert b"/BaseFont /Courier" in pdf, "base-14 font must not be embedded"


class TestPdfLayout:
    def test_no_line_exceeds_the_printable_column(self):
        pdf = render_pdf(bundle(conversations=[_long_conversation()]))
        drawn = re.findall(rb"\((.*?)\) Tj", pdf)
        assert drawn
        assert max(len(line) for line in drawn) <= COLUMNS

    def test_paginates_long_documents(self):
        convo = _long_conversation()
        pdf = render_pdf(bundle(conversations=[convo]))
        lines = _document_lines(bundle(conversations=[convo]))
        expected = -(-len(lines) // LINES_PER_PAGE)  # ceiling division
        assert int(re.search(rb"/Count (\d+)", pdf).group(1)) == expected
        assert expected > 1, "fixture should be long enough to need several pages"

    def test_empty_export_still_produces_one_valid_page(self):
        pdf = render_pdf(
            {"exported_at": "", "app_version": "", "documents": [], "conversations": []}
        )
        assert int(re.search(rb"/Count (\d+)", pdf).group(1)) == 1
        _, count, entries = parse_xref(pdf)
        assert len(entries) == count

    def test_escapes_characters_that_would_break_a_pdf_string(self):
        pdf = render_pdf(
            bundle(
                conversations=[
                    {
                        "title": "t",
                        "created_at": "",
                        "updated_at": "",
                        "messages": [
                            {
                                "role": "user",
                                "content": r"paren ( ) and back\slash",
                                "created_at": "",
                                "sources": [],
                            }
                        ],
                    }
                ]
            )
        )
        for line in re.findall(rb"\((.*?)\) Tj", pdf):
            # An unescaped ")" would terminate the string early, so every literal
            # paren inside the drawn text must be preceded by a backslash.
            assert re.search(rb"(?<!\\)\)", line) is None

    def test_folds_typography_to_ascii(self):
        """WinAnsi cannot hold an em dash, so it must not reach the encoder."""
        pdf = render_pdf(
            bundle(
                conversations=[
                    {
                        "title": "t",
                        "created_at": "",
                        "updated_at": "",
                        "messages": [
                            {
                                "role": "assistant",
                                "content": "a — b … c",
                                "created_at": "",
                                "sources": [],
                            }
                        ],
                    }
                ]
            )
        )
        pdf.decode("latin-1")  # must not raise
        assert "a - b ... c" in " ".join(
            x.decode("latin-1") for x in re.findall(rb"\((.*?)\) Tj", pdf)
        )

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            # ϕ U+03D5 is not φ U+03C6; a maths corpus uses both.
            ("ϕ(n)", "phi(n)"),
            ("φ(n)", "phi(n)"),
            ("≤", "<="),
            ("≠", "!="),  # NFKD would split this into "=" + combining slash
            ("½", "1/2"),  # NFKD introduces a fraction slash of its own
            ("x²", "x2"),
            ("oﬁce", "ofice"),
            ("a — b", "a - b"),
        ],
    )
    def test_unicode_survives_as_readable_ascii(self, source, expected):
        """Every one of these reaches the reader intact.

        They are the characters that actually turn into `?` if the folding is
        wrong, and a `?` in a maths answer reads as a broken export rather than
        as a symbol the encoder could not represent.
        """
        assert _to_ascii(source) == expected

    def test_transliterates_maths_rather_than_dropping_it(self):
        """A formulae-heavy corpus must not come out full of `?`.

        `?` reads as a broken export, and a reader cannot tell whether the
        symbol was lost or the PDF is damaged.
        """
        pdf = render_pdf(
            bundle(
                conversations=[
                    {
                        "title": "t",
                        "created_at": "",
                        "updated_at": "",
                        "messages": [
                            {
                                "role": "assistant",
                                "content": "phi(n) = (p-1)(q-1) and x <= y",
                                "created_at": "",
                                "sources": [],
                            }
                        ],
                    }
                ]
            )
        )
        drawn = " ".join(x.decode("latin-1") for x in re.findall(rb"\((.*?)\) Tj", pdf))
        # The drawn text is PDF-escaped, so parentheses arrive as \( \).
        assert r"phi\(n\)" in drawn
        assert "<=" in drawn
        assert "?" not in drawn


def _long_conversation(messages: int = 40):
    return {
        "title": "Long",
        "created_at": "",
        "updated_at": "",
        "messages": [
            {
                "role": "user",
                "content": ("word " * 40 + "\n") * 30,
                "created_at": "",
                "sources": [],
            }
            for _ in range(messages)
        ],
    }


class TestFilename:
    @pytest.mark.parametrize(
        ("extension", "expected_suffix"),
        [("md", ".md"), ("txt", ".txt"), ("pdf", ".pdf")],
    )
    def test_carries_the_extension_and_a_timestamp(self, extension, expected_suffix):
        name = suggested_filename(bundle(), extension)
        assert name.endswith(expected_suffix)
        assert name.startswith("marginalia-export-")

    def test_falls_back_when_the_timestamp_is_missing(self):
        assert suggested_filename({"exported_at": ""}, "pdf").endswith(".pdf")
