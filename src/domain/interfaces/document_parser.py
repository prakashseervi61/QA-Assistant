from abc import ABC, abstractmethod
from typing import BinaryIO


class DocumentParser(ABC):
    @abstractmethod
    async def parse(self, file: BinaryIO) -> str:
        pass

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        pass
