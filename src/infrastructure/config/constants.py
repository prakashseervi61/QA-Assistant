SUPPORTED_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_TOP_K = 5

MAX_FILE_SIZE_MB = 50
MAX_UPLOAD_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
