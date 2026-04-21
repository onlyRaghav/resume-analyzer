from django.contrib import admin

from .models import AnalysisRequestLog, AnalysisResult


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("uuid", "original_filename", "status", "overall_score", "share_enabled", "created_at")
    list_filter = ("status", "share_enabled", "created_at")
    search_fields = ("uuid", "original_filename", "target_job_title")
    readonly_fields = ("uuid", "created_at", "updated_at", "expires_at")


@admin.register(AnalysisRequestLog)
class AnalysisRequestLogAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "created_at")
    search_fields = ("ip_address",)
