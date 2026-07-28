from typing import BinaryIO

from docx import Document as DocxDocument

from src.domain.interfaces.document_parser import DocumentParser


class DOCXParser(DocumentParser):
    async def parse(self, file: BinaryIO) -> str:
        doc = DocxDocument(file)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)

    def get_supported_extensions(self) -> list[str]:
        return [".docx"]
