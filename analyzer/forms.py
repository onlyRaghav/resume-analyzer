from pathlib import Path

from django import forms
from django.conf import settings


class ResumeUploadForm(forms.Form):
    resume_file = forms.FileField(
        label="Resume file",
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.docx", "class": "file-input"}),
    )
    target_job_title = forms.CharField(
        label="Target job title or role",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Senior Backend Engineer at a fintech startup",
                "class": "form-input",
            }
        ),
    )
    job_description = forms.CharField(
        label="Paste job description",
        required=False,
        max_length=settings.RESUMEIQ_MAX_JOB_DESCRIPTION_CHARS,
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "maxlength": settings.RESUMEIQ_MAX_JOB_DESCRIPTION_CHARS,
                "class": "form-textarea",
                "placeholder": "Optional: paste the role description for deeper contextual matching.",
            }
        ),
    )

    def clean_resume_file(self):
        uploaded = self.cleaned_data["resume_file"]
        extension = Path(uploaded.name).suffix.lower()
        if extension not in settings.RESUMEIQ_ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Unsupported file type. Please upload a PDF or DOCX file.")
        if uploaded.size > settings.RESUMEIQ_MAX_UPLOAD_BYTES:
            raise forms.ValidationError("File exceeds the 5 MB limit.")
        return uploaded
