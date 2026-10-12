"""Export renderers — turn an export bundle into a file the user can keep.

Each renderer takes the same mapping the `/export` endpoint produces and returns
bytes (or a string) ready to write. Keeping them behind one module means the
route picks a format with a single lookup and no branching, and adding a format
is a new function here plus one line in the route — not a new endpoint.
"""

from infrastructure.export.markdown import render_markdown
from infrastructure.export.pdf import render_pdf, suggested_filename
from infrastructure.export.plaintext import render_text

__all__ = ["render_markdown", "render_pdf", "render_text", "suggested_filename"]
