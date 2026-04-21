from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.files.base import File
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .forms import ResumeUploadForm
from .models import AnalysisRequestLog, AnalysisResult, AnalysisStatus
from .services.queue import queue_analysis_job
from .services.security import FileValidationError, validate_uploaded_file


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def build_upload_context(form: ResumeUploadForm) -> dict:
    return {
        "form": form,
        "max_upload_mb": settings.RESUMEIQ_MAX_UPLOAD_BYTES // (1024 * 1024),
        "job_description_limit": settings.RESUMEIQ_MAX_JOB_DESCRIPTION_CHARS,
    }


class LandingView(View):
    template_name = "analyzer/landing.html"

    def get(self, request):
        return render(request, self.template_name, build_upload_context(ResumeUploadForm()))

    def post(self, request):
        form = ResumeUploadForm(request.POST, request.FILES)
        ip = client_ip(request)
        window_start = timezone.now() - timedelta(hours=1)
        recent_count = AnalysisRequestLog.objects.filter(ip_address=ip, created_at__gte=window_start).count()
        if recent_count >= settings.RESUMEIQ_RATE_LIMIT_PER_HOUR:
            form.add_error(None, "Too many analyses from this IP. Please wait and try again later.")
            return render(request, self.template_name, build_upload_context(form), status=429)

        if not form.is_valid():
            return render(request, self.template_name, build_upload_context(form), status=400)

        uploaded = form.cleaned_data["resume_file"]
        try:
            mime_type = validate_uploaded_file(uploaded)
        except FileValidationError as exc:
            form.add_error("resume_file", str(exc))
            return render(request, self.template_name, build_upload_context(form), status=400)

        result = AnalysisResult.objects.create(
            original_filename=uploaded.name,
            content_type=mime_type,
            target_job_title=form.cleaned_data["target_job_title"],
            job_description=form.cleaned_data["job_description"],
            expires_at=timezone.now() + timedelta(days=settings.RESUMEIQ_RESULT_RETENTION_DAYS),
        )

        extension = Path(uploaded.name).suffix.lower()
        stored_name = f"{result.uuid}{extension}"
        result.stored_file.save(stored_name, File(uploaded), save=True)

        AnalysisRequestLog.objects.create(ip_address=ip)
        queue_analysis_job(result.id)
        return redirect(result.get_analyzing_url())


class AnalyzingView(TemplateView):
    template_name = "analyzer/analyzing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = get_object_or_404(AnalysisResult, uuid=kwargs["uuid"])
        if result.is_expired:
            raise Http404("This result has expired.")
        context["result"] = result
        return context


class ResultStatusView(View):
    def get(self, request, uuid):
        result = get_object_or_404(AnalysisResult, uuid=uuid)
        if result.is_expired:
            return HttpResponse('<div class="status-card status-card--error">This result has expired.</div>', status=404)

        min_display_seconds = max(0, settings.RESUMEIQ_MIN_ANALYSIS_DISPLAY_SECONDS)
        ready_for_redirect = timezone.now() >= result.created_at + timedelta(seconds=min_display_seconds)

        if result.status == AnalysisStatus.COMPLETE:
            if not ready_for_redirect:
                return HttpResponse(
                    '<div class="status-card">Your analysis is complete. We are polishing the dashboard and will open it in a moment.</div>'
                )
            url = reverse("analyzer:results", kwargs={"uuid": result.uuid})
            html = (
                f'<div class="status-card status-card--success">'
                f'Analysis complete. <a href="{url}" class="inline-link">View your dashboard</a>.'
                f"</div>"
            )
            response = HttpResponse(html)
            response["HX-Redirect"] = url
            return response

        if result.status == AnalysisStatus.FAILED:
            return HttpResponse(
                f'<div class="status-card status-card--error">{result.error_message}</div>',
                status=200,
            )

        return HttpResponse(
            '<div class="status-card">We are reading your resume, scoring each section, and preparing your dashboard.</div>'
        )


class ResultsBaseView(TemplateView):
    template_name = "analyzer/results.html"
    shared_mode = False

    def get_result(self, uuid):
        result = get_object_or_404(AnalysisResult, uuid=uuid)
        if result.is_expired:
            raise Http404("This result has expired.")
        if self.shared_mode and not result.share_enabled:
            raise Http404("Share link is not active.")
        return result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = self.get_result(kwargs["uuid"])
        if result.status != AnalysisStatus.COMPLETE:
            context["pending_redirect"] = result.get_analyzing_url()
            return context
        context["result"] = result
        context["shared_mode"] = self.shared_mode
        context["share_url"] = self.request.build_absolute_uri(result.get_share_url())
        return context

    def render_to_response(self, context, **response_kwargs):
        pending_redirect = context.get("pending_redirect")
        if pending_redirect:
            return redirect(pending_redirect)
        return super().render_to_response(context, **response_kwargs)


class ResultsView(ResultsBaseView):
    pass


class SharedResultsView(ResultsBaseView):
    shared_mode = True


class GenerateShareLinkView(View):
    def post(self, request, uuid):
        result = get_object_or_404(AnalysisResult, uuid=uuid)
        result.share_enabled = True
        result.save(update_fields=["share_enabled", "updated_at"])
        share_url = request.build_absolute_uri(result.get_share_url())
        messages.success(request, "Share link created.")
        return HttpResponse(
            f'<div class="share-box"><input class="share-input" type="text" value="{share_url}" readonly />'
            f'<button class="button button--secondary" type="button" '
            f'onclick="navigator.clipboard.writeText(\'{share_url}\')">Copy URL</button></div>'
        )


class ErrorView(TemplateView):
    template_name = "analyzer/error.html"
