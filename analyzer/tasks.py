import logging
from pathlib import Path

from django.utils import timezone

try:
    from celery import shared_task
except ImportError:  # pragma: no cover
    def shared_task(*_args, **_kwargs):
        bind = _kwargs.get("bind", False)

        def decorator(func):
            def wrapped(*args, **kwargs):
                if bind:
                    return func(None, *args, **kwargs)
                return func(*args, **kwargs)

            wrapped.delay = wrapped
            return wrapped

        return decorator

from .models import AnalysisResult, AnalysisStatus
from .services.ai import AnalysisInput, AnalysisProviderError, get_analysis_provider
from .services.extraction import ExtractionError, extract_resume_text

logger = logging.getLogger(__name__)


def build_failure_reference(failure_at) -> str:
    return timezone.localtime(failure_at).strftime("%Y%m%d-%H%M%S")


def delete_stored_file(result: AnalysisResult) -> None:
    if result.stored_file:
        result.stored_file.delete(save=False)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    dont_autoretry_for=(ExtractionError, AnalysisProviderError),
    retry_kwargs={"max_retries": 1, "countdown": 2},
)
def run_analysis(self, result_id: int):
    result = AnalysisResult.objects.get(pk=result_id)
    result.status = AnalysisStatus.PROCESSING
    result.error_message = ""
    result.save(update_fields=["status", "error_message", "updated_at"])

    file_path = Path(result.stored_file.path)

    try:
        extracted_text = extract_resume_text(file_path)
        provider = get_analysis_provider()
        analysis = provider.analyze(
            AnalysisInput(
                resume_text=extracted_text,
                target_job_title=result.target_job_title,
                job_description=result.job_description,
            )
        )

        result.extracted_text = extracted_text
        result.overall_score = analysis["overall_score"]
        result.hire_probability = analysis["hire_probability"]
        result.summary = analysis["summary"]
        result.sections = analysis["sections"]
        result.strengths = analysis["strengths"]
        result.improvements = analysis["improvements"]
        result.keywords_missing = analysis["keywords_missing"]
        result.keywords_found = analysis.get("keywords_found", [])
        result.ats_risk = analysis["ats_risk"]
        result.ats_risk_explanation = analysis["ats_risk_explanation"]
        result.raw_analysis = analysis
        result.status = AnalysisStatus.COMPLETE
        result.error_message = ""
        result.save()
        delete_stored_file(result)
    except ExtractionError as exc:
        failure_at = timezone.now()
        failure_ref = build_failure_reference(failure_at)
        logger.warning(
            "Extraction failed for result %s at %s: %s",
            result.uuid,
            failure_ref,
            exc,
        )
        result.mark_failed(str(exc), failure_at=failure_at)
        delete_stored_file(result)
    except AnalysisProviderError as exc:
        failure_at = timezone.now()
        failure_ref = build_failure_reference(failure_at)
        logger.exception(
            "Analysis provider failed for result %s at %s: %s",
            result.uuid,
            failure_ref,
            exc,
        )
        result.mark_failed(
            f"The analysis provider rejected the request. Please verify the AI provider configuration. Reference: {failure_ref}.",
            failure_at=failure_at,
        )
        delete_stored_file(result)
    except Exception as exc:  # pragma: no cover
        failure_at = timezone.now()
        failure_ref = build_failure_reference(failure_at)
        logger.exception(
            "Analysis failed for result %s at %s with %s: %s",
            result.uuid,
            failure_ref,
            exc.__class__.__name__,
            exc,
        )
        result.mark_failed(
            f"The analysis service is temporarily unavailable. Please try again. Reference: {failure_ref}.",
            failure_at=failure_at,
        )
        raise exc


@shared_task
def purge_expired_results():
    expired = AnalysisResult.objects.filter(expires_at__lt=timezone.now())
    deleted_count = expired.count()
    for item in expired:
        if item.stored_file:
            item.stored_file.delete(save=False)
    expired.delete()
    return deleted_count
