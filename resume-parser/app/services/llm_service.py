"""LLM integration: turn raw resume text into a validated `ResumeData` object.

Uses Claude's structured outputs (`client.messages.parse`): we pass the
`ResumeData` Pydantic model as the output format, the API constrains the reply
to that JSON schema, and the SDK validates it back into a `ResumeData`.
No manual JSON parsing or "please reply in JSON" prompt hacks needed.
"""

import os

import anthropic
from loguru import logger

from app.models import LLMServiceError, ResumeData

SYSTEM_PROMPT = """You are an expert resume parser. Extract information from the resume text \
the user provides and return it in the required structure.

Rules:
- Only use information present in the resume. Never invent or infer details that are not stated.
- If a field is missing, leave it null (or an empty list).
- Keep values as written (dates, phone formats, job titles), only trimming extra whitespace.
- List work experience and education in the order they appear (usually most recent first).
- responsibilities: one concise bullet per item, taken from the resume's own bullets or sentences.
- skills.technical: languages, frameworks, tools, platforms, methodologies.
  skills.soft: interpersonal skills such as communication or leadership. Only include soft
  skills the resume explicitly mentions.
- certifications: name of each certification (include issuer/year if stated)."""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Create the Claude client lazily so the app can start without an API key."""
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMServiceError("ANTHROPIC_API_KEY is not set on the server.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def extract_resume_data(resume_text: str) -> ResumeData:
    """Send resume text to Claude and return the structured result."""
    model = os.getenv("LLM_MODEL", "claude-haiku-5-5")
    log = logger.bind(model=model, text_chars=len(resume_text))
    log.info("Calling LLM for extraction")

    try:
        response = _get_client().messages.parse(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"<resume>\n{resume_text}\n</resume>"}
            ],
            output_format=ResumeData,
        )
    except anthropic.AuthenticationError as exc:
        log.error(f"LLM authentication failed: {exc}")
        raise LLMServiceError("LLM authentication failed. Check ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        log.warning(f"LLM rate limited: {exc}")
        raise LLMServiceError("LLM rate limit reached. Please retry shortly.") from exc
    except anthropic.APIConnectionError as exc:
        log.error(f"Could not reach LLM API: {exc}")
        raise LLMServiceError("Could not reach the LLM service.") from exc
    except anthropic.APIStatusError as exc:
        log.error(f"LLM API error {exc.status_code}: {exc}")
        raise LLMServiceError(f"LLM service returned an error ({exc.status_code}).") from exc

    if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
        log.error(f"Unusable LLM response, stop_reason={response.stop_reason}")
        raise LLMServiceError("The LLM did not return a complete result. Please retry.")

    log.bind(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    ).info("LLM extraction succeeded")
    return response.parsed_output
