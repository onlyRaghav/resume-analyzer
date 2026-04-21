import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class AnalysisStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"


class AnalysisResult(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    status = models.CharField(max_length=20, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING, db_index=True)
    original_filename = models.CharField(max_length=255)
    stored_file = models.FileField(upload_to="tmp/")
    content_type = models.CharField(max_length=120, blank=True)
    target_job_title = models.CharField(max_length=255, blank=True)
    job_description = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)
    overall_score = models.PositiveSmallIntegerField(null=True, blank=True)
    hire_probability = models.CharField(max_length=20, blank=True)
    summary = models.TextField(blank=True)
    sections = models.JSONField(default=list, blank=True)
    strengths = models.JSONField(default=list, blank=True)
    improvements = models.JSONField(default=list, blank=True)
    keywords_missing = models.JSONField(default=list, blank=True)
    keywords_found = models.JSONField(default=list, blank=True)
    ats_risk = models.CharField(max_length=20, blank=True)
    ats_risk_explanation = models.CharField(max_length=255, blank=True)
    raw_analysis = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    share_enabled = models.BooleanField(default=False)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.uuid})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=settings.RESUMEIQ_RESULT_RETENTION_DAYS)
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def score_band(self) -> str:
        if self.overall_score is None:
            return "neutral"
        if self.overall_score < 50:
            return "danger"
        if self.overall_score < 75:
            return "warning"
        return "success"

    def get_absolute_url(self) -> str:
        return reverse("analyzer:results", kwargs={"uuid": self.uuid})

    def get_analyzing_url(self) -> str:
        return reverse("analyzer:analyzing", kwargs={"uuid": self.uuid})

    def get_share_url(self) -> str:
        return reverse("analyzer:results-share", kwargs={"uuid": self.uuid})

    def mark_failed(self, message: str, failure_at=None):
        if failure_at is None:
            failure_at = timezone.now()
        self.status = AnalysisStatus.FAILED
        timestamp = timezone.localtime(failure_at).strftime("%Y-%m-%d %H:%M:%S %Z")
        self.error_message = f"{message} [logged_at={timestamp}]"
        self.save(update_fields=["status", "error_message", "updated_at"])


class AnalysisRequestLog(models.Model):
    ip_address = models.GenericIPAddressField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.ip_address} @ {self.created_at.isoformat()}"
