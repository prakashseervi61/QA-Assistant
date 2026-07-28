from src.domain.interfaces.document_parser import DocumentParser

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def create_parser(file_extension: str) -> DocumentParser:
    ext = file_extension.lower()

    if ext == ".pdf":
        from src.infrastructure.document_processing.pdf_parser import PDFParser
        return PDFParser()

    elif ext == ".docx":
        from src.infrastructure.document_processing.docx_parser import DOCXParser
        return DOCXParser()

    elif ext == ".txt":
        from src.infrastructure.document_processing.txt_parser import TXTParser
        return TXTParser()

    else:
        raise ValueError(
            f"Unsupported file type: {ext}. "
            f"Supported types: {sorted(_SUPPORTED_EXTENSIONS)}"
        )
