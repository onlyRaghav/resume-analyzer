import hashlib
import json
import re
from dataclasses import dataclass
from urllib import error, parse, request

from django.conf import settings


class AnalysisProviderError(Exception):
    pass


@dataclass
class AnalysisInput:
    resume_text: str
    target_job_title: str = ""
    job_description: str = ""


class BaseAnalysisProvider:
    required_fields = {
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
    }

    def validate_analysis(self, payload: dict) -> dict:
        missing = self.required_fields.difference(payload.keys())
        if missing:
            raise AnalysisProviderError(f"Analysis response is missing required fields: {', '.join(sorted(missing))}.")

        payload["overall_score"] = max(0, min(100, int(payload["overall_score"])))
        payload["sections"] = [self._normalize_section(section) for section in payload["sections"]]
        payload["strengths"] = [str(item).strip() for item in payload["strengths"] if str(item).strip()][:5]
        payload["improvements"] = [str(item).strip() for item in payload["improvements"] if str(item).strip()][:5]
        payload["keywords_missing"] = [str(item).strip() for item in payload["keywords_missing"] if str(item).strip()][:12]
        payload["keywords_found"] = [str(item).strip() for item in payload["keywords_found"] if str(item).strip()][:12]
        payload["hire_probability"] = str(payload["hire_probability"]).strip()
        payload["summary"] = str(payload["summary"]).strip()
        payload["ats_risk"] = str(payload["ats_risk"]).strip()
        payload["ats_risk_explanation"] = str(payload["ats_risk_explanation"]).strip()
        return payload

    @staticmethod
    def _normalize_section(section: dict) -> dict:
        return {
            "name": str(section.get("name", "")).strip(),
            "score": max(0, min(100, int(section.get("score", 0)))),
            "feedback": str(section.get("feedback", "")).strip(),
        }


class PlaceholderAnalysisProvider(BaseAnalysisProvider):
    core_keywords = [
        "python",
        "django",
        "flask",
        "fastapi",
        "api",
        "rest",
        "sql",
        "postgresql",
        "mysql",
        "mongodb",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "linux",
        "git",
        "testing",
        "pytest",
        "ci",
        "cd",
        "analytics",
        "etl",
        "leadership",
        "communication",
        "stakeholder",
        "agile",
        "javascript",
        "typescript",
        "react",
        "node",
    ]
    section_headers = {
        "experience": "Experience",
        "work": "Experience",
        "employment": "Experience",
        "projects": "Projects",
        "skills": "Skills",
        "education": "Education",
        "certifications": "Certifications",
        "summary": "Summary",
        "profile": "Summary",
    }
    stopwords = {
        "about",
        "across",
        "after",
        "also",
        "and",
        "build",
        "built",
        "candidate",
        "clear",
        "collaborate",
        "communication",
        "create",
        "data",
        "deliver",
        "design",
        "engineer",
        "engineering",
        "ensure",
        "experience",
        "for",
        "from",
        "have",
        "into",
        "looking",
        "need",
        "role",
        "resume",
        "senior",
        "skills",
        "software",
        "strong",
        "team",
        "with",
        "work",
        "years",
    }
    action_verbs = {
        "built",
        "created",
        "delivered",
        "designed",
        "developed",
        "drove",
        "improved",
        "implemented",
        "increased",
        "launched",
        "led",
        "managed",
        "optimized",
        "owned",
        "reduced",
        "scaled",
        "shipped",
    }

    def __init__(self, model_id: str, access_token: str = ""):
        self.model_id = model_id
        self.access_token = access_token

    def analyze(self, payload: AnalysisInput) -> dict:
        fingerprint = hashlib.sha256(payload.resume_text.encode("utf-8")).hexdigest()[:10]
        signals = self._collect_signals(payload)
        found_keywords = signals["found_keywords"]
        missing_keywords = signals["missing_keywords"]
        sections = [
            self._section("Skills", signals["skills_score"], self._skills_feedback(signals)),
            self._section("Experience", signals["experience_score"], self._experience_feedback(signals)),
            self._section("Education", signals["education_score"], self._education_feedback(signals)),
            self._section("Formatting", signals["formatting_score"], self._formatting_feedback(signals)),
            self._section("Keywords/ATS", signals["keywords_score"], self._keywords_feedback(signals)),
            self._section("Impact & Achievements", signals["impact_score"], self._impact_feedback(signals)),
        ]
        overall_score = round(
            (
                signals["skills_score"]
                + signals["experience_score"]
                + signals["education_score"]
                + signals["formatting_score"]
                + signals["keywords_score"]
                + signals["impact_score"]
            )
            / 6
        )
        hire_probability = self._hire_probability(overall_score)
        ats_risk = self._ats_risk(signals, overall_score)
        summary = self._summary(signals, hire_probability)
        return self.validate_analysis(
            {
                "overall_score": overall_score,
                "hire_probability": hire_probability,
                "summary": summary,
                "sections": sections,
                "strengths": self._build_strengths(signals),
                "improvements": self._build_improvements(signals),
                "keywords_missing": missing_keywords,
                "keywords_found": found_keywords,
                "ats_risk": ats_risk,
                "ats_risk_explanation": self._ats_risk_explanation(signals, ats_risk),
                "provider_meta": {
                    "provider": "placeholder",
                    "model_id": self.model_id,
                    "token_configured": bool(self.access_token),
                    "analysis_mode": "heuristic",
                    "fingerprint": fingerprint,
                },
            }
        )

    @staticmethod
    def _section(name: str, score: int, feedback: str) -> dict:
        score = max(0, min(100, score))
        return {"name": name, "score": score, "feedback": feedback}

    @staticmethod
    def _hire_probability(score: int) -> str:
        if score < 50:
            return "Low"
        if score < 70:
            return "Medium"
        if score < 85:
            return "High"
        return "Very High"

    @classmethod
    def _collect_signals(cls, payload: AnalysisInput) -> dict:
        resume_text = payload.resume_text
        resume_lower = resume_text.lower()
        job_corpus = f"{payload.target_job_title} {payload.job_description}".lower()
        resume_tokens = set(cls._tokenize(resume_text))
        target_keywords = cls._extract_target_keywords(payload)
        found_keywords = [keyword for keyword in target_keywords if keyword in resume_lower][:12]
        missing_keywords = [keyword for keyword in target_keywords if keyword not in resume_lower][:12]
        lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
        bullet_lines = [line for line in lines if re.match(r"^[-*•]\s+", line)]
        metric_hits = len(re.findall(r"\b\d+%?\b|\$\d+|₹\d+|\b\d+\+\b", resume_text))
        action_verb_hits = sum(1 for token in resume_tokens if token in cls.action_verbs)
        section_names = {name for name in cls.section_headers if re.search(rf"\b{name}\b", resume_lower)}
        has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", resume_text))
        has_phone = bool(re.search(r"(\+\d{1,3}\s*)?[\(]?\d{3,4}[\)]?[-\s]?\d{3}[-\s]?\d{3,4}", resume_text))
        has_linkedin = "linkedin.com" in resume_lower
        has_github = "github.com" in resume_lower
        word_count = len(cls._tokenize(resume_text))
        line_density = round(word_count / max(1, len(lines)), 2)
        coverage = len(found_keywords) / max(1, len(target_keywords))

        skills_score = 45 + round(coverage * 45)
        if len(found_keywords) >= 5:
            skills_score += 6
        if "skills" in section_names:
            skills_score += 4

        experience_score = 42 + min(24, action_verb_hits * 4) + min(18, len(bullet_lines) * 2) + min(12, metric_hits * 2)
        if "experience" in section_names or "work" in section_names:
            experience_score += 4

        education_score = 50
        if "education" in section_names:
            education_score += 20
        if re.search(r"\b(b\.?tech|m\.?tech|bachelor|master|degree|university|college|certification)\b", resume_lower):
            education_score += 15
        if "certifications" in section_names:
            education_score += 5

        formatting_score = 48
        formatting_score += 8 if has_email else 0
        formatting_score += 8 if has_phone else 0
        formatting_score += 6 if has_linkedin or has_github else 0
        formatting_score += 10 if len(section_names) >= 3 else 4 if len(section_names) >= 2 else 0
        formatting_score += 8 if 5 <= line_density <= 18 else 0
        formatting_score += 6 if len(bullet_lines) >= 4 else 0

        keywords_score = 40 + round(coverage * 50)
        if payload.job_description.strip():
            keywords_score += 5

        impact_score = 38 + min(28, metric_hits * 4) + min(18, action_verb_hits * 3)
        if re.search(r"\b(improved|reduced|increased|grew|saved|optimized|scaled)\b", resume_lower):
            impact_score += 8

        return {
            "resume_text": resume_text,
            "resume_lower": resume_lower,
            "target_keywords": target_keywords,
            "found_keywords": found_keywords,
            "missing_keywords": missing_keywords,
            "coverage": coverage,
            "lines": lines,
            "bullet_lines": bullet_lines,
            "metric_hits": metric_hits,
            "action_verb_hits": action_verb_hits,
            "section_names": section_names,
            "has_email": has_email,
            "has_phone": has_phone,
            "has_linkedin": has_linkedin,
            "has_github": has_github,
            "word_count": word_count,
            "skills_score": max(0, min(100, skills_score)),
            "experience_score": max(0, min(100, experience_score)),
            "education_score": max(0, min(100, education_score)),
            "formatting_score": max(0, min(100, formatting_score)),
            "keywords_score": max(0, min(100, keywords_score)),
            "impact_score": max(0, min(100, impact_score)),
        }

    @classmethod
    def _extract_target_keywords(cls, payload: AnalysisInput) -> list[str]:
        corpus = f"{payload.target_job_title} {payload.job_description}".lower()
        target = [keyword for keyword in cls.core_keywords if keyword in corpus]
        for token in cls._tokenize(corpus):
            if len(token) < 4 or token in cls.stopwords or token in target:
                continue
            target.append(token)
            if len(target) >= 12:
                break
        if not target:
            target = ["python", "django", "testing", "communication", "api"]
        return target[:12]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z][a-zA-Z0-9.+#-]*", text.lower())

    @staticmethod
    def _summary(signals: dict, hire_probability: str) -> str:
        coverage_pct = round(signals["coverage"] * 100)
        return (
            f"This resume shows a {hire_probability.lower()} level of readiness based on structure, keyword coverage, and evidence of impact. "
            f"It currently matches about {coverage_pct}% of the targeted role language, and the strongest gains would come from clearer achievements and sharper role-specific phrasing."
        )

    @staticmethod
    def _ats_risk(signals: dict, overall_score: int) -> str:
        risk_points = 0
        if not signals["has_email"] or not signals["has_phone"]:
            risk_points += 1
        if len(signals["section_names"]) < 2:
            risk_points += 1
        if signals["coverage"] < 0.35:
            risk_points += 1
        if len(signals["bullet_lines"]) < 3:
            risk_points += 1
        if overall_score < 55:
            risk_points += 1
        if risk_points >= 3:
            return "High"
        if risk_points >= 1:
            return "Medium"
        return "Low"

    @staticmethod
    def _ats_risk_explanation(signals: dict, ats_risk: str) -> str:
        if ats_risk == "Low":
            return "The resume appears structurally readable for ATS systems and already includes a useful share of target-role language."
        if ats_risk == "Medium":
            return "The resume should be parseable, but missing keywords or inconsistent structure may reduce match confidence in automated screening."
        return "The resume may struggle in ATS screening because key role terms, clear sections, or scannable bullet structure are too limited."

    @staticmethod
    def _skills_feedback(signals: dict) -> str:
        if signals["coverage"] >= 0.7:
            return "Skills align well with the target role, and the resume reflects many of the expected technical terms."
        if signals["coverage"] >= 0.4:
            return "The core skill base is relevant, but the resume would benefit from naming more role-specific tools and concepts."
        return "The skill story feels broad, but more of the target role's exact language should appear explicitly in the resume."

    @staticmethod
    def _experience_feedback(signals: dict) -> str:
        if signals["action_verb_hits"] >= 6 and len(signals["bullet_lines"]) >= 4:
            return "Experience is presented with clear ownership and action-led phrasing, which improves credibility."
        if len(signals["bullet_lines"]) >= 3:
            return "Experience is readable, though some bullets could better emphasize ownership, scope, and outcomes."
        return "Experience needs stronger bullet structure so hiring teams can quickly scan responsibilities and achievements."

    @staticmethod
    def _education_feedback(signals: dict) -> str:
        if signals["education_score"] >= 75:
            return "Education and credentials are easy to spot and provide enough context for a quick review."
        if signals["education_score"] >= 60:
            return "Education is present, but the section could be easier to scan or slightly more complete."
        return "Education details are limited or hard to find, which can weaken confidence during fast screening."

    @staticmethod
    def _formatting_feedback(signals: dict) -> str:
        if signals["formatting_score"] >= 78:
            return "Formatting is generally ATS-friendly and easy to scan, with clear sections and contact details."
        if signals["formatting_score"] >= 60:
            return "Formatting is workable, but clearer sectioning and more consistent bullets would improve readability."
        return "Formatting likely slows down scanning because contact details, sections, or bullet structure are not consistent enough."

    @staticmethod
    def _keywords_feedback(signals: dict) -> str:
        if signals["coverage"] >= 0.7:
            return "Keyword targeting is strong, which should improve both ATS matching and recruiter relevance."
        if signals["coverage"] >= 0.4:
            return "Keyword coverage is moderate, with several target terms still missing from the resume."
        return "Keyword coverage is weak for the target role, so the resume may underperform in ATS filtering."

    @staticmethod
    def _impact_feedback(signals: dict) -> str:
        if signals["metric_hits"] >= 4:
            return "There is good evidence of impact because the resume includes multiple quantified results or scale indicators."
        if signals["metric_hits"] >= 2:
            return "Some impact is visible, though the strongest bullets would benefit from more concrete numbers and outcomes."
        return "Impact is not yet obvious enough; adding metrics, scale, or before-and-after outcomes would strengthen the case."

    @staticmethod
    def _build_strengths(signals: dict) -> list[str]:
        strengths = []
        if signals["coverage"] >= 0.55:
            strengths.append("Relevant role keywords are already present across the resume.")
        if signals["action_verb_hits"] >= 5:
            strengths.append("Experience bullets use action-oriented language that signals ownership.")
        if signals["metric_hits"] >= 3:
            strengths.append("Several achievements include numbers or scale indicators, which improves credibility.")
        if len(signals["section_names"]) >= 3:
            strengths.append("The resume has recognizable sections that make it easier to scan quickly.")
        if signals["has_linkedin"] or signals["has_github"]:
            strengths.append("Professional links add useful context beyond the resume itself.")
        if not strengths:
            strengths.append("The resume contains enough baseline structure to build a stronger targeted version.")
        return strengths[:5]

    @staticmethod
    def _build_improvements(signals: dict) -> list[str]:
        improvements = []
        if signals["coverage"] < 0.7 and signals["missing_keywords"]:
            improvements.append(
                f"Add more exact target-role terms such as {', '.join(signals['missing_keywords'][:3])}."
            )
        if signals["metric_hits"] < 3:
            improvements.append("Add measurable outcomes to key bullets so your impact is easier to trust at a glance.")
        if len(signals["bullet_lines"]) < 4:
            improvements.append("Rewrite dense paragraphs into concise bullets to improve recruiter and ATS scanning.")
        if not signals["has_linkedin"] and not signals["has_github"]:
            improvements.append("Include a professional profile or portfolio link if it supports the role you want.")
        if "skills" not in signals["section_names"]:
            improvements.append("Create a dedicated skills section so the strongest tools and technologies are easy to find.")
        return improvements[:5]


class GeminiAnalysisProvider(BaseAnalysisProvider):
    api_url_template = "https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"

    def __init__(self, model_id: str, access_token: str):
        if not access_token:
            raise AnalysisProviderError("GEMINI_API_KEY is required for the Gemini provider.")
        self.model_id = model_id
        self.access_token = access_token

    def analyze(self, payload: AnalysisInput) -> dict:
        body = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": self._system_instruction(),
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": self._build_user_prompt(payload),
                        }
                    ],
                }
            ],
            "generationConfig": self._generation_config(),
        }
        raw = self._post_json(body)
        content = self._extract_content(raw)
        try:
            parsed = self._parse_json_content(content)
            used_fallback = False
        except AnalysisProviderError as exc:
            if "valid JSON" not in str(exc):
                raise
            parsed = self._repair_json_response(content)
            used_fallback = True
        parsed["provider_meta"] = {
            "provider": "gemini",
            "model_id": self.model_id,
            "used_json_repair": used_fallback,
        }
        return self.validate_analysis(parsed)

    def _post_json(self, body: dict) -> dict:
        api_url = self.api_url_template.format(model_id=parse.quote(self.model_id, safe=""))
        http_request = request.Request(
            api_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-goog-api-key": self.access_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise AnalysisProviderError(f"Gemini API request failed with status {exc.code}: {detail[:300]}") from exc
        except error.URLError as exc:
            raise AnalysisProviderError("Unable to reach the Gemini API.") from exc
        except TimeoutError as exc:
            raise AnalysisProviderError("The Gemini request timed out.") from exc

    @staticmethod
    def _extract_content(raw: dict) -> str:
        try:
            parts = raw["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise AnalysisProviderError("Unexpected Gemini response shape.") from exc

    @staticmethod
    def _parse_json_content(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError as exc:
                    raise AnalysisProviderError("Model response was not valid JSON.") from exc
            raise AnalysisProviderError("Model response was not valid JSON.")

    def _repair_json_response(self, malformed_content: str) -> dict:
        repair_body = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "You repair malformed resume-analysis output. "
                            "Return only valid JSON that matches the required schema exactly. "
                            "Do not add markdown fences, commentary, or extra keys."
                        ),
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "The following model output was intended to be JSON but is malformed. "
                                "Repair it into valid JSON using the same meaning where possible. "
                                "If any field is incomplete, infer a concise safe value that preserves the intended analysis.\n\n"
                                f"Malformed output:\n{malformed_content}"
                            ),
                        }
                    ],
                }
            ],
            "generationConfig": self._generation_config(),
        }
        repaired_raw = self._post_json(repair_body)
        repaired_content = self._extract_content(repaired_raw)
        return self._parse_json_content(repaired_content)

    @staticmethod
    def _system_instruction() -> str:
        return (
            "You are an expert resume analyst. Return only valid JSON with this exact shape: "
            '{"overall_score":0,"hire_probability":"","summary":"","sections":[{"name":"","score":0,"feedback":""}],'
            '"strengths":[],"improvements":[],"keywords_missing":[],"keywords_found":[],"ats_risk":"","ats_risk_explanation":""}. '
            "Use integer scores from 0 to 100. Provide 3 to 5 concise strengths and improvements. "
            "Do not include markdown fences or extra commentary."
        )

    def _generation_config(self) -> dict:
        return {
            "temperature": 0.2,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
            "responseSchema": self._response_schema(),
        }

    @staticmethod
    def _response_schema() -> dict:
        return {
            "type": "OBJECT",
            "required": [
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
            "properties": {
                "overall_score": {"type": "INTEGER"},
                "hire_probability": {"type": "STRING"},
                "summary": {"type": "STRING"},
                "sections": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "required": ["name", "score", "feedback"],
                        "properties": {
                            "name": {"type": "STRING"},
                            "score": {"type": "INTEGER"},
                            "feedback": {"type": "STRING"},
                        },
                    },
                },
                "strengths": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "improvements": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "keywords_missing": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "keywords_found": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "ats_risk": {"type": "STRING"},
                "ats_risk_explanation": {"type": "STRING"},
            },
        }

    @staticmethod
    def _build_user_prompt(payload: AnalysisInput) -> str:
        job_title = payload.target_job_title.strip() or "General resume review"
        job_description = payload.job_description.strip() or "No job description provided."
        return (
            f"Target job title or role:\n{job_title}\n\n"
            f"Job description:\n{job_description}\n\n"
            "Resume text:\n"
            f"{payload.resume_text}\n\n"
            "Evaluate the resume for hire-readiness, ATS fit, clarity, impact, and missing keywords."
        )


def get_analysis_provider():
    provider_name = settings.RESUMEIQ_ANALYSIS_PROVIDER
    if provider_name == "placeholder":
        return PlaceholderAnalysisProvider(
            model_id=settings.RESUMEIQ_GEMINI_MODEL_ID,
            access_token=settings.RESUMEIQ_GEMINI_API_KEY,
        )
    if provider_name == "gemini":
        return GeminiAnalysisProvider(
            model_id=settings.RESUMEIQ_GEMINI_MODEL_ID,
            access_token=settings.RESUMEIQ_GEMINI_API_KEY,
        )
    raise AnalysisProviderError(f"Unsupported analysis provider '{provider_name}'.")
