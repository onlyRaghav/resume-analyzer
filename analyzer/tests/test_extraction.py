from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from analyzer.services.extraction import ExtractionError, extract_resume_text, sanitize_text


def write_docx(path: Path, text: str):
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    document.save(path)


class ExtractionTests(SimpleTestCase):
    def make_docx_path(self) -> Path:
        path = settings.BASE_DIR / f"test-{uuid4().hex}.docx"
        self.addCleanup(lambda: path.exists() and path.unlink())
        return path

    def test_sanitize_text_collapses_whitespace(self):
        self.assertEqual(sanitize_text("Hello \n\n world\t\t!"), "Hello world !")

    @override_settings(RESUMEIQ_MIN_EXTRACTED_WORDS=3)
    def test_extract_docx_text(self):
        docx_path = self.make_docx_path()
        write_docx(docx_path, "One two three four five")
        self.assertIn("One two three", extract_resume_text(docx_path))

    @override_settings(RESUMEIQ_MIN_EXTRACTED_WORDS=10)
    def test_short_text_raises_error(self):
        docx_path = self.make_docx_path()
        write_docx(docx_path, "Short text")
        with self.assertRaises(ExtractionError):
            extract_resume_text(docx_path)
