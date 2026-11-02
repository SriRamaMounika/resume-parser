"""Resume parsing logic: validate the upload, extract its text, and store results.

Storage is file based. For each upload with ID <id>:
  data/uploads/<id>.pdf|.docx   the original file
  data/uploads/<id>.json        the extraction result (a ResumeResponse)
"""

import io
import os
import uuid
from pathlib import Path

import pymupdf
from docx import Document
from loguru import logger

from app.models import (
    FileTooLargeError,
    ResumeNotFoundError,
    ResumeResponse,
    TextExtractionError,
    UnsupportedFileTypeError,
)

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


# --- Validation & text extraction --------------------------------------------


def validate_file(filename: str, content: bytes) -> str:
    """Check extension and size. Returns the lower-cased extension (e.g. '.pdf')."""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{extension or 'none'}'. Upload a PDF or DOCX file."
        )
    if not content:
        raise TextExtractionError("The uploaded file is empty.")

    max_mb = int(os.getenv("MAX_UPLOAD_MB", "5"))
    if len(content) > max_mb * 1024 * 1024:
        raise FileTooLargeError(f"File exceeds the {max_mb} MB limit.")
    return extension


def extract_text(content: bytes, extension: str) -> str:
    """Extract text from PDF or DOCX bytes. Raises TextExtractionError on failure."""
    try:
        text = _extract_pdf(content) if extension == ".pdf" else _extract_docx(content)
    except Exception as exc:
        logger.bind(extension=extension).warning(f"Text extraction failed: {exc}")
        raise TextExtractionError("Could not read the file. It may be corrupted.") from exc

    text = text.strip()
    if not text:
        # Typically a scanned (image-only) PDF; OCR is out of scope.
        raise TextExtractionError("No text found in the file (is it a scanned image?).")
    return text


def _extract_pdf(content: bytes) -> str:
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        return "\n".join(page.get_text() for page in pdf)


def _extract_docx(content: bytes) -> str:
    document = Document(io.BytesIO(content))
    lines = [paragraph.text for paragraph in document.paragraphs]
    # Many resume templates put content in tables, so read those too.
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines)


# --- Storage -----------------------------------------------------------------


def new_document_id() -> str:
    return str(uuid.uuid4())


def save_result(result: ResumeResponse, extension: str, content: bytes) -> None:
    """Store the original file and its extraction result under the document ID."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{result.document_id}{extension}").write_bytes(content)
    (UPLOAD_DIR / f"{result.document_id}.json").write_text(result.model_dump_json(indent=2))


def load_result(document_id: str) -> ResumeResponse:
    """Load a stored result. Raises ResumeNotFoundError if it doesn't exist."""
    # Only accept real UUIDs, which also prevents path traversal (e.g. "../x").
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise ResumeNotFoundError(f"Resume '{document_id}' not found.") from None

    path = UPLOAD_DIR / f"{document_id}.json"
    if not path.exists():
        raise ResumeNotFoundError(f"Resume '{document_id}' not found.")
    return ResumeResponse.model_validate_json(path.read_text())
