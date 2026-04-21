import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from analyzer.services.ai import AnalysisInput, AnalysisProviderError, get_analysis_provider


class PlaceholderProviderTests(SimpleTestCase):
    @override_settings(RESUMEIQ_ANALYSIS_PROVIDER="placeholder")
    def test_placeholder_response_shape(self):
        provider = get_analysis_provider()
        payload = AnalysisInput(
            resume_text="Python Django Docker leadership communication testing " * 12,
            target_job_title="Senior Django Engineer",
            job_description="We need Python, Django, Docker, AWS, testing, and leadership.",
        )
        result = provider.analyze(payload)
        self.assertEqual(
            sorted(result.keys()),
            sorted(
                [
                    "overall_score",
                    "hire_probability",
                    "summary",
                    "sections",
                    "strengths",
                    "improvements",
                    "keywords_missing",
                    "keywords_found",
                    "ats_risk",
                    "ats_risk_explanation",
                    "provider_meta",
                ]
            ),
        )
        self.assertEqual(result["provider_meta"]["provider"], "placeholder")
        self.assertEqual(result["provider_meta"]["analysis_mode"], "heuristic")
        self.assertTrue(result["strengths"])
        self.assertTrue(result["improvements"])
        self.assertTrue(result["keywords_found"])

    @override_settings(RESUMEIQ_ANALYSIS_PROVIDER="placeholder")
    def test_placeholder_uses_role_specific_keyword_coverage(self):
        provider = get_analysis_provider()
        result = provider.analyze(
            AnalysisInput(
                resume_text=(
                    "john@example.com\n"
                    "+91 9876543210\n"
                    "LinkedIn: linkedin.com/in/johndoe\n"
                    "Skills\nPython Django PostgreSQL Docker pytest REST API AWS\n"
                    "Experience\n"
                    "- Built APIs for customer workflows\n"
                    "- Improved deployment speed by 35%\n"
                    "- Reduced incident volume by 20%\n"
                    "Education\nBachelor of Technology in Computer Science\n"
                ),
                target_job_title="Senior Django Engineer",
                job_description="Need Python, Django, PostgreSQL, Docker, AWS, testing, REST API, and leadership.",
            )
        )
        self.assertGreaterEqual(result["overall_score"], 70)
        self.assertIn("python", result["keywords_found"])
        self.assertIn("django", result["keywords_found"])
        self.assertNotEqual(result["ats_risk"], "High")

    @override_settings(RESUMEIQ_ANALYSIS_PROVIDER="unknown")
    def test_unknown_provider_raises_error(self):
        with self.assertRaises(AnalysisProviderError):
            get_analysis_provider()

    @override_settings(
        RESUMEIQ_ANALYSIS_PROVIDER="gemini",
        RESUMEIQ_GEMINI_API_KEY="gemini_test",
        RESUMEIQ_GEMINI_MODEL_ID="gemini-2.5-flash",
    )
    @patch("analyzer.services.ai.request.urlopen")
    def test_gemini_provider_parses_generate_content_response(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "overall_score": 81,
                                            "hire_probability": "High",
                                            "summary": "Strong match with a few keyword gaps.",
                                            "sections": [
                                                {"name": "Skills", "score": 82, "feedback": "Good technical baseline."},
                                                {"name": "Experience", "score": 79, "feedback": "Impact could be more quantified."},
                                            ],
                                            "strengths": ["Clear focus", "Good technical depth", "Readable structure"],
                                            "improvements": ["Add metrics", "Mirror target keywords", "Tighten bullets"],
                                            "keywords_missing": ["aws"],
                                            "keywords_found": ["python", "django"],
                                            "ats_risk": "Medium",
                                            "ats_risk_explanation": "Some important matching phrases are still missing.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")

        provider = get_analysis_provider()
        result = provider.analyze(
            AnalysisInput(
                resume_text="Python Django testing leadership delivery " * 15,
                target_job_title="Senior Django Engineer",
                job_description="Need Python, Django, AWS, testing, and API design.",
            )
        )
        request_payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))

        self.assertEqual(result["overall_score"], 81)
        self.assertEqual(result["provider_meta"]["provider"], "gemini")
        self.assertEqual(request_payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("responseSchema", request_payload["generationConfig"])
        self.assertEqual(
            request_payload["generationConfig"]["responseSchema"]["required"],
            [
                "overall_score",
                "hire_probability",
                "summary",
                "sections",
                "strengths",
                "improvements",
                "keywords_missing",
                "keywords_found",
                "ats_risk",
                "ats_risk_explanation",
            ],
        )
        self.assertFalse(result["provider_meta"]["used_json_repair"])

    @override_settings(
        RESUMEIQ_ANALYSIS_PROVIDER="gemini",
        RESUMEIQ_GEMINI_API_KEY="gemini_test",
        RESUMEIQ_GEMINI_MODEL_ID="gemini-2.5-flash",
    )
    @patch("analyzer.services.ai.request.urlopen")
    def test_gemini_provider_retries_with_json_repair_on_invalid_json(self, mock_urlopen):
        broken_response = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"overall_score":81,"hire_probability":"High","summary":"Broken',
                                }
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")
        repaired_response = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "overall_score": 81,
                                            "hire_probability": "High",
                                            "summary": "Strong match after JSON repair.",
                                            "sections": [
                                                {"name": "Skills", "score": 82, "feedback": "Good technical baseline."},
                                                {"name": "Experience", "score": 79, "feedback": "Impact could be more quantified."},
                                            ],
                                            "strengths": ["Clear focus", "Good technical depth", "Readable structure"],
                                            "improvements": ["Add metrics", "Mirror target keywords", "Tighten bullets"],
                                            "keywords_missing": ["aws"],
                                            "keywords_found": ["python", "django"],
                                            "ats_risk": "Medium",
                                            "ats_risk_explanation": "Some important matching phrases are still missing.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")

        mock_urlopen.side_effect = [
            type("ResponseContext", (), {"__enter__": lambda self: type("Resp", (), {"read": lambda self: broken_response})(), "__exit__": lambda self, exc_type, exc, tb: False})(),
            type("ResponseContext", (), {"__enter__": lambda self: type("Resp", (), {"read": lambda self: repaired_response})(), "__exit__": lambda self, exc_type, exc, tb: False})(),
        ]

        provider = get_analysis_provider()
        result = provider.analyze(
            AnalysisInput(
                resume_text="Python Django testing leadership delivery " * 15,
                target_job_title="Senior Django Engineer",
                job_description="Need Python, Django, AWS, testing, and API design.",
            )
        )

        self.assertEqual(result["overall_score"], 81)
        self.assertTrue(result["provider_meta"]["used_json_repair"])
        self.assertEqual(mock_urlopen.call_count, 2)

        first_request_payload = json.loads(mock_urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        second_request_payload = json.loads(mock_urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertEqual(first_request_payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("Malformed output:", second_request_payload["contents"][0]["parts"][0]["text"])

    @override_settings(
        RESUMEIQ_ANALYSIS_PROVIDER="gemini",
        RESUMEIQ_GEMINI_API_KEY="",
        RESUMEIQ_GEMINI_MODEL_ID="gemini-2.5-flash",
    )
    def test_gemini_provider_requires_token(self):
        with self.assertRaises(AnalysisProviderError):
            get_analysis_provider()
