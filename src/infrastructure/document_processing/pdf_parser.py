from typing import BinaryIO

from PyPDF2 import PdfReader

from src.domain.interfaces.document_parser import DocumentParser


class PDFParser(DocumentParser):
    async def parse(self, file: BinaryIO) -> str:
        reader = PdfReader(file)
        text_parts = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        return "\n\n".join(text_parts)

    def get_supported_extensions(self) -> list[str]:
        return [".pdf"]
