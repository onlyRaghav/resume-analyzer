import re
from pathlib import Path

from django.conf import settings
from docx import Document

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None


class ExtractionError(Exception):
    pass


def sanitize_text(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0B-\x1F\x7F]", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_pdf_text(file_path: Path) -> str:
    if fitz is None:
        raise ExtractionError("PDF parsing dependency is not installed. Please install PyMuPDF.")

    chunks = []
    with fitz.open(file_path) as document:
        for page in document:
            chunks.append(page.get_text("text"))
    return sanitize_text(" ".join(chunks))


def extract_docx_text(file_path: Path) -> str:
    document = Document(file_path)
    chunks = [paragraph.text for paragraph in document.paragraphs]
    return sanitize_text(" ".join(chunks))


def extract_resume_text(file_path: Path) -> str:
    extension = file_path.suffix.lower()
    if extension == ".pdf":
        text = extract_pdf_text(file_path)
    elif extension == ".docx":
        text = extract_docx_text(file_path)
    else:
        raise ExtractionError("Unsupported file type.")

    if len(text.split()) < settings.RESUMEIQ_MIN_EXTRACTED_WORDS:
        raise ExtractionError(
            "We could not read your resume. Please ensure it contains selectable text (not a scanned image)."
        )
    return text
