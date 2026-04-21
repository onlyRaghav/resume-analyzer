import tempfile
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from analyzer.models import AnalysisResult, AnalysisStatus
from analyzer.services.ai import AnalysisProviderError
from analyzer.tasks import run_analysis


def build_analysis_payload() -> dict:
    return {
        "overall_score": 82,
        "hire_probability": "High",
        "summary": "Strong resume.",
        "sections": [],
        "strengths": ["Clear impact"],
        "improvements": ["Add more metrics"],
        "keywords_missing": ["Kubernetes"],
        "keywords_found": ["Python"],
        "ats_risk": "Low",
        "ats_risk_explanation": "Formatting looks parseable.",
    }


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class RunAnalysisTaskTests(TestCase):
    def create_result_with_file(self) -> AnalysisResult:
        result = AnalysisResult.objects.create(
            original_filename="resume.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            expires_at=timezone.now() + timedelta(days=1),
        )
        result.stored_file.save(f"{result.uuid}.docx", ContentFile(b"test file"), save=True)
        return result

    @patch("analyzer.tasks.extract_resume_text", return_value="python django testing delivery leadership")
    @patch("analyzer.tasks.get_analysis_provider")
    def test_successful_analysis_deletes_uploaded_file(self, mock_get_provider, _mock_extract):
        result = self.create_result_with_file()
        stored_name = result.stored_file.name
        provider = Mock()
        provider.analyze.return_value = build_analysis_payload()
        mock_get_provider.return_value = provider

        run_analysis(result.id)

        result.refresh_from_db()
        self.assertEqual(result.status, AnalysisStatus.COMPLETE)
        self.assertFalse(default_storage.exists(stored_name))

    @patch("analyzer.tasks.extract_resume_text", return_value="python django testing delivery leadership")
    @patch("analyzer.tasks.get_analysis_provider")
    def test_retryable_failure_keeps_uploaded_file_for_retry(self, mock_get_provider, _mock_extract):
        result = self.create_result_with_file()
        stored_name = result.stored_file.name
        provider = Mock()
        provider.analyze.side_effect = RuntimeError("provider unavailable")
        mock_get_provider.return_value = provider

        with self.assertRaises(RuntimeError):
            run_analysis(result.id)

        result.refresh_from_db()
        self.assertEqual(result.status, AnalysisStatus.FAILED)
        self.assertTrue(default_storage.exists(stored_name))

    @patch("analyzer.tasks.extract_resume_text", return_value="python django testing delivery leadership")
    @patch("analyzer.tasks.get_analysis_provider")
    def test_provider_failure_fails_once_and_deletes_uploaded_file(self, mock_get_provider, _mock_extract):
        result = self.create_result_with_file()
        stored_name = result.stored_file.name
        provider = Mock()
        provider.analyze.side_effect = AnalysisProviderError("forbidden")
        mock_get_provider.return_value = provider

        run_analysis(result.id)

        result.refresh_from_db()
        self.assertEqual(result.status, AnalysisStatus.FAILED)
        self.assertIn("analysis provider rejected the request", result.error_message.lower())
        self.assertFalse(default_storage.exists(stored_name))
