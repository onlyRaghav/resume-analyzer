from django.test import TestCase
from django.utils import timezone

from analyzer.models import AnalysisResult, AnalysisStatus


class AnalysisResultModelTests(TestCase):
    def test_expiry_is_set_on_save(self):
        result = AnalysisResult.objects.create(
            original_filename="resume.docx",
            stored_file="tmp/resume.docx",
            expires_at=timezone.now(),
        )
        self.assertIsNotNone(result.expires_at)

    def test_score_band_reflects_score(self):
        result = AnalysisResult(
            original_filename="resume.docx",
            stored_file="tmp/resume.docx",
            expires_at=timezone.now(),
            overall_score=82,
            status=AnalysisStatus.COMPLETE,
        )
        self.assertEqual(result.score_band, "success")

    def test_share_url_contains_uuid(self):
        result = AnalysisResult.objects.create(
            original_filename="resume.docx",
            stored_file="tmp/resume.docx",
            expires_at=timezone.now(),
        )
        self.assertIn(str(result.uuid), result.get_share_url())
