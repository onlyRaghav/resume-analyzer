from pathlib import Path

from django.conf import settings

try:
    import magic
except ImportError:  # pragma: no cover
    magic = None


PDF_MIME_TYPES = {"application/pdf"}
DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
}


class FileValidationError(Exception):
    pass


def validate_uploaded_file(uploaded_file) -> str:
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in settings.RESUMEIQ_ALLOWED_EXTENSIONS:
        raise FileValidationError("Unsupported file type. Please upload a PDF or DOCX file.")
    if uploaded_file.size > settings.RESUMEIQ_MAX_UPLOAD_BYTES:
        raise FileValidationError("File exceeds the 5 MB limit.")

    if magic is None:
        return ""

    head = uploaded_file.read(4096)
    uploaded_file.seek(0)
    mime = magic.from_buffer(head, mime=True)

    if extension == ".pdf" and mime not in PDF_MIME_TYPES:
        raise FileValidationError("The uploaded file does not appear to be a valid PDF.")
    if extension == ".docx" and mime not in DOCX_MIME_TYPES:
        raise FileValidationError("The uploaded file does not appear to be a valid DOCX document.")
    return mime
