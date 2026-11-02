"""FastAPI app: endpoints and error handling.

Run with:  uvicorn app.main:app --reload
Docs at:   http://localhost:8000/docs
"""

from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.models import ErrorResponse, ResumeParserError, ResumeResponse
from app.services import llm_service, parser
from app.utils.logger import setup_logging

load_dotenv()  # read .env into environment variables
setup_logging()

app = FastAPI(
    title="Resume Parser API",
    description="Upload a PDF/DOCX resume and get structured data extracted by an LLM.",
    version="1.0.0",
)


# --- Error handling ----------------------------------------------------------


@app.exception_handler(ResumeParserError)
async def handle_known_error(request: Request, exc: ResumeParserError) -> JSONResponse:
    """Expected errors (bad file, LLM failure, not found) -> their own status code."""
    logger.bind(path=request.url.path, status=exc.status_code).warning(exc.message)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Anything else is a bug: log the traceback, hide internals from the client."""
    logger.bind(path=request.url.path).exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# --- Endpoints ---------------------------------------------------------------


@app.post(
    "/api/upload",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["resumes"],
    responses={
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Not a PDF/DOCX"},
        422: {"model": ErrorResponse, "description": "No readable text in file"},
        502: {"model": ErrorResponse, "description": "LLM extraction failed"},
    },
)
async def upload_resume(file: UploadFile = File(..., description="PDF or DOCX resume")) -> ResumeResponse:
    """Upload a resume, extract its information with the LLM and store the result."""
    filename = file.filename or "unknown"
    content = await file.read()
    log = logger.bind(filename=filename, size_bytes=len(content))
    log.info("Received upload")

    extension = parser.validate_file(filename, content)
    text = parser.extract_text(content, extension)
    data = llm_service.extract_resume_data(text)

    # Persist only after a successful extraction, so every ID maps to a result.
    result = ResumeResponse(
        document_id=parser.new_document_id(),
        filename=filename,
        created_at=datetime.now(timezone.utc),
        data=data,
    )
    parser.save_result(result, extension, content)

    log.bind(document_id=result.document_id).info("Resume processed")
    return result


@app.get(
    "/api/resume/{document_id}",
    response_model=ResumeResponse,
    tags=["resumes"],
    responses={404: {"model": ErrorResponse, "description": "Resume not found"}},
)
def get_resume(document_id: str) -> ResumeResponse:
    """Return a previously extracted resume by its document ID."""
    return parser.load_result(document_id)
