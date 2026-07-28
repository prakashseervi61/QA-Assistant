from typing import BinaryIO

from src.domain.interfaces.document_parser import DocumentParser


class TXTParser(DocumentParser):
    async def parse(self, file: BinaryIO) -> str:
        content = file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return content

    def get_supported_extensions(self) -> list[str]:
        return [".txt"]
