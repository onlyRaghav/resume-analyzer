import tempfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from analyzer.models import AnalysisRequestLog, AnalysisResult, AnalysisStatus


def make_docx_bytes(text: str) -> bytes:
    from docx import Document

    buffer = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=tempfile.gettempdir(), RESUMEIQ_MIN_EXTRACTED_WORDS=3)
class UploadFlowTests(TestCase):
    @patch("analyzer.views.validate_uploaded_file", return_value="")
    @patch("analyzer.views.queue_analysis_job")
    def test_successful_upload_redirects_to_analyzing(self, mock_queue, _mock_validate):
        upload = SimpleUploadedFile(
            "resume.docx",
            make_docx_bytes("Python Django leadership testing delivery"),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(reverse("analyzer:landing"), {"resume_file": upload})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AnalysisResult.objects.count(), 1)
        mock_queue.assert_called_once()

    def test_rate_limit_blocks_excess_requests(self):
        for _ in range(5):
            AnalysisRequestLog.objects.create(ip_address="127.0.0.1")
        upload = SimpleUploadedFile(
            "resume.docx",
            make_docx_bytes("Python Django leadership testing delivery"),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(reverse("analyzer:landing"), {"resume_file": upload})
        self.assertEqual(response.status_code, 429)

    @override_settings(RESUMEIQ_MIN_ANALYSIS_DISPLAY_SECONDS=0)
    def test_results_status_redirects_when_complete(self):
        result = AnalysisResult.objects.create(
            original_filename="resume.docx",
            stored_file="tmp/resume.docx",
            status=AnalysisStatus.COMPLETE,
            overall_score=80,
            hire_probability="High",
            summary="Strong baseline.",
            sections=[],
            strengths=[],
            improvements=[],
            keywords_missing=[],
            keywords_found=[],
            ats_risk="Low",
            ats_risk_explanation="Looks good.",
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get(reverse("analyzer:results-status", kwargs={"uuid": result.uuid}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response.headers)

    @override_settings(RESUMEIQ_MIN_ANALYSIS_DISPLAY_SECONDS=8)
    def test_results_status_waits_before_redirect_when_complete_too_quickly(self):
        result = AnalysisResult.objects.create(
            original_filename="resume.docx",
            stored_file="tmp/resume.docx",
            status=AnalysisStatus.COMPLETE,
            overall_score=80,
            hire_probability="High",
            summary="Strong baseline.",
            sections=[],
            strengths=[],
            improvements=[],
            keywords_missing=[],
            keywords_found=[],
            ats_risk="Low",
            ats_risk_explanation="Looks good.",
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get(reverse("analyzer:results-status", kwargs={"uuid": result.uuid}))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Redirect", response.headers)
        self.assertContains(response, "Your analysis is complete. We are polishing the dashboard")

    def test_shared_results_requires_share_enabled(self):
        result = AnalysisResult.objects.create(
            original_filename="resume.docx",
            stored_file="tmp/resume.docx",
            status=AnalysisStatus.COMPLETE,
            overall_score=80,
            hire_probability="High",
            summary="Strong baseline.",
            sections=[],
            strengths=[],
            improvements=[],
            keywords_missing=[],
            keywords_found=[],
            ats_risk="Low",
            ats_risk_explanation="Looks good.",
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get(reverse("analyzer:results-share", kwargs={"uuid": result.uuid}))
        self.assertEqual(response.status_code, 404)
