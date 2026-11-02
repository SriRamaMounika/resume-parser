"""Streamlit front end. Talks to the FastAPI backend over HTTP only.

Run with:  streamlit run ui/streamlit_app.py --client.toolbarMode minimal
(the flag hides Streamlit's Deploy button and developer menu items)
"""

import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))  # keep in sync with the API's limit


def call_api(method: str, path: str, **kwargs) -> dict | None:
    """Call the backend; show the API's error message and return None on failure."""
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=180, **kwargs)
    except requests.ConnectionError:
        st.error(f"Cannot reach the API at {API_URL}. Is the backend running?")
        return None
    if not response.ok:
        detail = response.json().get("detail", response.text)
        st.error(f"Error {response.status_code}: {detail}")
        return None
    return response.json()


def show_resume(result: dict) -> None:
    """Render one extracted resume as organised sections."""
    data = result["data"]
    contact, skills = data["contact"], data["skills"]

    st.success(f"Document ID: `{result['document_id']}`  ·  {result['filename']}")

    with st.container(border=True):
        st.subheader("👤 Contact")
        cols = st.columns(4)
        for col, (label, key) in zip(
            cols, [("Name", "name"), ("Email", "email"), ("Phone", "phone"), ("Location", "location")]
        ):
            col.markdown(f"**{label}**  \n{contact.get(key) or '—'}")

    if data["summary"]:
        with st.container(border=True):
            st.subheader("📝 Summary")
            st.write(data["summary"])

    with st.container(border=True):
        st.subheader("💼 Work Experience")
        if not data["work_experience"]:
            st.caption("None found")
        for job in data["work_experience"]:
            st.markdown(f"**{job['role'] or 'Role'}** · {job['company'] or 'Company'}")
            if job["duration"]:
                st.caption(job["duration"])
            for item in job["responsibilities"]:
                st.markdown(f"- {item}")

    with st.container(border=True):
        st.subheader("🎓 Education")
        if not data["education"]:
            st.caption("None found")
        for edu in data["education"]:
            year = f" ({edu['year']})" if edu["year"] else ""
            st.markdown(f"**{edu['degree'] or 'Degree'}** · {edu['institution'] or ''}{year}")

    with st.container(border=True):
        st.subheader("🛠️ Skills")
        left, right = st.columns(2)
        left.markdown("**Technical**  \n" + (", ".join(skills["technical"]) or "—"))
        right.markdown("**Soft**  \n" + (", ".join(skills["soft"]) or "—"))

    if data["certifications"]:
        with st.container(border=True):
            st.subheader("📜 Certifications")
            for cert in data["certifications"]:
                st.markdown(f"- {cert}")

    with st.expander("Raw JSON"):
        st.json(result)


st.set_page_config(page_title="Resume Parser", page_icon="📄", layout="wide")
st.title("📄 Resume Parser")
st.caption("Upload a PDF or DOCX resume to extract structured information with an LLM.")

uploaded = st.file_uploader("Resume file", type=["pdf", "docx"], max_upload_size=MAX_UPLOAD_MB)
if st.button("Extract", type="primary", disabled=uploaded is None):
    with st.spinner("Extracting information... this can take a few seconds."):
        files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
        st.session_state["result"] = call_api("POST", "/api/upload", files=files)

if st.session_state.get("result"):
    show_resume(st.session_state["result"])
