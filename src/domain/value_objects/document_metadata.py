from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DocumentMetadata:
    filename: str = ""
    file_type: str = ""
    file_size: int = 0
    page_count: Optional[int] = None
    author: Optional[str] = None
    created_date: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "page_count": self.page_count,
            "author": self.author,
            "created_date": self.created_date,
        }
