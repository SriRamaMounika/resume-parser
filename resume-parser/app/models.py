"""Pydantic models for the extracted resume data and the API responses.

Also defines the error types the services raise (bottom of file).

`ResumeData` doubles as the LLM output schema: the Claude SDK turns it into a
JSON schema, and the model's answer is validated back into this class.
Fields are optional / default to empty lists because not every resume has
every section.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    name: str | None = Field(None, description="Candidate's full name")
    email: str | None = Field(None, description="Email address")
    phone: str | None = Field(None, description="Phone number as written")
    location: str | None = Field(None, description="City, state/region, country")


class WorkExperience(BaseModel):
    company: str | None = None
    role: str | None = Field(None, description="Job title")
    duration: str | None = Field(None, description="e.g. 'Jan 2020 - Present'")
    responsibilities: list[str] = Field(
        default_factory=list, description="Key responsibilities and achievements"
    )


class Education(BaseModel):
    degree: str | None = Field(None, description="Degree and field of study")
    institution: str | None = None
    year: str | None = Field(None, description="Graduation year or date range")


class Skills(BaseModel):
    technical: list[str] = Field(
        default_factory=list, description="Languages, tools, frameworks, platforms"
    )
    soft: list[str] = Field(
        default_factory=list, description="Interpersonal / non-technical skills"
    )


class ResumeData(BaseModel):
    """Everything we extract from a single resume."""

    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: str | None = Field(None, description="Professional summary or objective")
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    certifications: list[str] = Field(default_factory=list)


class ResumeResponse(BaseModel):
    """Response body for both POST /api/upload and GET /api/resume/{id}."""

    document_id: str
    filename: str
    created_at: datetime
    data: ResumeData


class ErrorResponse(BaseModel):
    """Shape of every error response, so clients can rely on `detail`."""

    detail: str


# --- Errors -----------------------------------------------------------------
# Raised by the services. Each one carries the HTTP status it maps to, so
# main.py turns all of them into a JSON error response with a single handler.


class ResumeParserError(Exception):
    """Base class for all expected, user-facing errors."""

    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileTypeError(ResumeParserError):
    """The uploaded file is not a PDF or DOCX."""

    status_code = 415


class FileTooLargeError(ResumeParserError):
    """The uploaded file exceeds the configured size limit."""

    status_code = 413


class TextExtractionError(ResumeParserError):
    """The file could not be read, or contains no extractable text."""

    status_code = 422


class LLMServiceError(ResumeParserError):
    """The LLM call failed or returned an unusable response."""

    status_code = 502


class ResumeNotFoundError(ResumeParserError):
    """No stored result exists for the requested document ID."""

    status_code = 404
