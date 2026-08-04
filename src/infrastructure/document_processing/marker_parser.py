"""Marker-based PDF parser for high-quality layout-aware extraction."""

import logging
import tempfile
from typing import BinaryIO

from src.domain.interfaces.document_parser import DocumentParser

logger = logging.getLogger(__name__)

# Check if marker-pdf is available at import time
try:
    from marker.config.parser import ConfigParser  # type: ignore[import-untyped]
    from marker.convert import (
        convert_single_pdf,  # type: ignore[import-untyped]  # noqa: E501
    )
    from marker.models import create_model_dict  # type: ignore[import-untyped]

    _marker_available = True
except ImportError:
    _marker_available = False
    convert_single_pdf = None  # type: ignore[assignment,misc]
    ConfigParser = None  # type: ignore[assignment,misc]
    create_model_dict = None  # type: ignore[assignment,misc]


class MarkerParser(DocumentParser):
    """PDF parser using marker-pdf for layout-aware extraction.

    Extracts tables as Markdown, preserves headers, and handles
    multi-column layouts.
    """

    def __init__(self) -> None:
        self._models: object = None

    def _get_models(self) -> object:
        if self._models is None and create_model_dict is not None:
            self._models = create_model_dict()
        return self._models

    def _parse_sync(self, file: BinaryIO) -> str:
        if not _marker_available:
            raise ImportError(
                "marker-pdf is required for MarkerParser. "
                "Install with: pip install marker-pdf"
            )

        models = self._get_models()
        config = ConfigParser(
            pipetables=True,
            force_ocr=False,
            output_format="markdown",
        )

        content = file.read()

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            rendered = convert_single_pdf(
                tmp_path,
                config=config,
                models=models,
            )
            return rendered.markdown
        finally:
            import os

            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    async def parse(self, file: BinaryIO) -> str:
        import asyncio

        return await asyncio.to_thread(self._parse_sync, file)

    def get_supported_extensions(self) -> list[str]:
        return [".pdf"]
