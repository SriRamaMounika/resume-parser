# Resume Parser

Upload a resume (PDF or DOCX) and get structured information back: contact details,
summary, work experience, education, skills and certifications. Extraction is done by
an LLM (Anthropic Claude). The project has a **FastAPI** backend and a **Streamlit** UI.

## How it works

```
Streamlit UI ──HTTP──▶ FastAPI (app/main.py)
                          │
                          ├─ parser.validate_file()      check type (.pdf/.docx) and size
                          ├─ parser.extract_text()       PyMuPDF / python-docx → plain text
                          ├─ llm_service.extract_resume_data()
                          │      Claude structured outputs → validated ResumeData model
                          └─ parser.save_result()        data/uploads/<id>.{pdf,docx,json}
```

1. **Validate** the file: only `.pdf` / `.docx`, not empty, at most `MAX_UPLOAD_MB`.
2. **Extract text**: PyMuPDF for PDFs; python-docx for DOCX, reading both paragraphs and tables.
3. **LLM extraction**: the text goes to Claude through `client.messages.parse(output_format=ResumeData)`.
   The `ResumeData` Pydantic model becomes the JSON schema the reply must follow, and the SDK
   validates the reply back into `ResumeData`. No JSON parsing or retrying on bad JSON is needed.
4. **Store** the original file and the result JSON under a new UUID, then return the result.

### Prompting approach

The system prompt (`app/services/llm_service.py`) tells the model to:
- use only facts in the resume and never invent details (missing fields stay `null` or `[]`),
- keep values as written (dates, phone formats, titles),
- keep the resume's order for jobs and education,
- split skills into technical and soft, listing soft skills only when the resume states them.

The resume text goes inside `<resume>` tags so the model can tell the document apart from
the instructions. The output structure itself is enforced by the schema, so the prompt
covers only *what* to extract, not the format.

## Project structure

```
resume-parser/
├── README.md
├── requirements.txt
├── .env.example            # Example environment variables
├── app/
│   ├── main.py             # FastAPI app: endpoints + error handlers
│   ├── models.py           # Pydantic models (+ error types)
│   ├── services/
│   │   ├── parser.py       # Validation, text extraction, file storage
│   │   └── llm_service.py  # Claude integration (prompt + structured output)
│   └── utils/
│       └── logger.py       # loguru setup
├── ui/
│   └── streamlit_app.py    # Upload, extract, display results
└── data/
    └── uploads/            # Uploaded files and <id>.json results
```

## Setup

Requires **Python 3.10+**.

```bash
cd resume-parser
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then set ANTHROPIC_API_KEY in .env
```

## Run

Start the API and the UI in two terminals (both from the `resume-parser/` folder, with the venv active):

```bash
uvicorn app.main:app --reload
```

```bash
streamlit run ui/streamlit_app.py --client.toolbarMode minimal
```

- UI: http://localhost:8501
- API docs (Swagger, auto-generated): http://localhost:8000/docs

## API

### `POST /api/upload`

Multipart form with a `file` field (PDF or DOCX). Returns `201 Created`:

```bash
curl -F "file=@/path/to/resume.pdf" http://localhost:8000/api/upload
```

```json
{
  "document_id": "3f6c1e2a-...",
  "filename": "resume.pdf",
  "created_at": "2026-11-01T12:00:00Z",
  "data": {
    "contact": {"name": "Jane Doe", "email": "jane@example.com", "phone": "+1 555 0100", "location": "Austin, TX"},
    "summary": "Backend engineer with 6 years ...",
    "work_experience": [
      {"company": "Acme", "role": "Senior Engineer", "duration": "2021 - Present",
       "responsibilities": ["Led migration to ...", "..."]}
    ],
    "education": [{"degree": "B.S. Computer Science", "institution": "UT Austin", "year": "2018"}],
    "skills": {"technical": ["Python", "FastAPI", "AWS"], "soft": ["Mentoring"]},
    "certifications": ["AWS Certified Developer"]
  }
}
```

### `GET /api/resume/{document_id}`

Returns the same response shape for a stored result, or `404` if none exists.

```bash
curl http://localhost:8000/api/resume/3f6c1e2a-...
```

### Errors

Every error returns `{"detail": "<message>"}`.

| Status | When |
|--------|------|
| 404 | Unknown `document_id` |
| 413 | File larger than `MAX_UPLOAD_MB` |
| 415 | File is not `.pdf` / `.docx` |
| 422 | Empty, corrupted or image-only file (no text), or no `file` field in the request |
| 502 | LLM call failed (missing/invalid API key, rate limit, network, incomplete reply) |
| 500 | Unexpected error (logged with a traceback; no internal details in the response) |

Each domain error is a class in `app/models.py` that carries its own status code.
`main.py` uses one exception handler to turn any of them into a JSON response,
so the services never import FastAPI.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | — (required) | Claude API key |
| `LLM_MODEL` | `claude-haiku-5-5` | Claude model used for extraction |
| `MAX_UPLOAD_MB` | `5` | Upload size limit (API and UI) |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_JSON` | `false` | `true` = one JSON log object per line |
| `API_URL` | `http://localhost:8000` | Backend URL used by the Streamlit UI |

## Design decisions

- **Structured outputs over "reply in JSON" prompting**: the schema is enforced by the API,
  so the response always matches `ResumeData`. One Pydantic model serves as the LLM schema,
  the API response model and the stored format.
- **Store only after a successful extraction**: every document ID always has a result.
- **File storage instead of a database**: simple and easy to inspect, and it survives restarts.
  Storage lives in two functions (`save_result` / `load_result`), so moving to a database
  would only change those.
- **Document IDs are UUIDs** and are checked as UUIDs on lookup, which also blocks path
  traversal such as `../`.
- **Synchronous LLM call**: each upload takes a few seconds, which is fine for this scope.
  At scale this would become a background job with a status endpoint.

## Limitations

- Scanned (image-only) PDFs are rejected because there is no OCR.
- No authentication, and uploaded files are kept on disk indefinitely.
