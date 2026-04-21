# ResumeIQ App Flow

This document explains how the app works end-to-end and points to the Python files responsible for each step.

## High-Level Overview

ResumeIQ is a Django app that lets a user upload a resume, optionally add a target job title and job description, and then receive an analysis result. The system:

1. serves the landing page and upload form
2. validates the uploaded file
3. stores an `AnalysisResult` record and the uploaded file
4. queues a background analysis job
5. extracts text from the resume
6. calls the configured AI provider
7. stores the structured analysis result
8. shows a polling page until analysis completes
9. renders a result dashboard and optional share link

## Main Runtime Flow

### 1. Request Entry and URL Routing

Incoming HTTP requests enter through Django and are routed into the analyzer app.

Responsible Python files:

- [core/wsgi.py](/d:/django-projects/core/wsgi.py)
- [core/asgi.py](/d:/django-projects/core/asgi.py)
- [core/urls.py](/d:/django-projects/core/urls.py)
- [analyzer/urls.py](/d:/django-projects/analyzer/urls.py)

What they do:

- `core/wsgi.py` and `core/asgi.py` boot Django.
- `core/urls.py` mounts the analyzer app at the site root.
- `analyzer/urls.py` maps each user-facing route to a class-based view.

### 2. Landing Page and Upload Submission

The landing page is shown by `LandingView`. On form submit, the same view handles the POST request.

Responsible Python files:

- [analyzer/views.py](/d:/django-projects/analyzer/views.py)
- [analyzer/forms.py](/d:/django-projects/analyzer/forms.py)
- [analyzer/context_processors.py](/d:/django-projects/analyzer/context_processors.py)

What happens:

- `LandingView.get()` renders the upload page.
- `LandingView.post()` receives the upload, applies rate limiting, validates the form, validates the file content type, creates the database row, stores the uploaded file, and queues analysis.
- `ResumeUploadForm` validates extension, upload size, and text inputs.
- `product_context()` injects shared template values like product name and privacy notice.

### 3. File Validation and Security Checks

Uploaded files are checked both by the form and by server-side MIME validation.

Responsible Python files:

- [analyzer/forms.py](/d:/django-projects/analyzer/forms.py)
- [analyzer/services/security.py](/d:/django-projects/analyzer/services/security.py)

What happens:

- The form ensures only `.pdf` and `.docx` are accepted and enforces the max upload size.
- `validate_uploaded_file()` uses `python-magic` when available to inspect the first bytes of the file and reject mismatched or invalid uploads.

### 4. Database Records and State Tracking

The app stores both the uploaded-analysis record and a simple IP-based request log for rate limiting.

Responsible Python files:

- [analyzer/models.py](/d:/django-projects/analyzer/models.py)
- [analyzer/migrations/0001_initial.py](/d:/django-projects/analyzer/migrations/0001_initial.py)

Main models:

- `AnalysisResult`
- `AnalysisRequestLog`

What `AnalysisResult` stores:

- upload metadata
- analysis status
- extracted text
- score and summary
- structured sections, strengths, improvements, and keywords
- error messages
- share state and expiry timestamps

What `AnalysisRequestLog` stores:

- IP address
- request timestamp

### 5. Queueing the Analysis Job

Once the upload is accepted, the app schedules background processing.

Responsible Python files:

- [analyzer/views.py](/d:/django-projects/analyzer/views.py)
- [analyzer/services/queue.py](/d:/django-projects/analyzer/services/queue.py)
- [analyzer/tasks.py](/d:/django-projects/analyzer/tasks.py)
- [core/celery.py](/d:/django-projects/core/celery.py)
- [core/__init__.py](/d:/django-projects/core/__init__.py)

What happens:

- `LandingView.post()` calls `queue_analysis_job(result.id)`.
- `queue_analysis_job()` tries to dispatch the Celery task with `.delay(...)`.
- If Celery dispatch fails and thread fallback is enabled, it runs the task in a background thread.
- `core/celery.py` configures the Celery app and autodiscovers tasks.

### 6. Background Analysis Task

The main analysis work happens in the `run_analysis` task.

Responsible Python files:

- [analyzer/tasks.py](/d:/django-projects/analyzer/tasks.py)

What `run_analysis()` does:

1. loads the `AnalysisResult`
2. marks it as `processing`
3. extracts text from the uploaded file
4. builds the provider input
5. calls the configured AI provider
6. stores all structured fields on the model
7. marks the result as `complete`
8. if anything fails, marks the result as `failed`
9. logs failures with timestamps and a reference token

Related cleanup task:

- `purge_expired_results()` deletes expired result rows and uploaded files

### 7. Resume Text Extraction

The uploaded file is converted into raw text before AI analysis begins.

Responsible Python files:

- [analyzer/services/extraction.py](/d:/django-projects/analyzer/services/extraction.py)

What happens:

- PDFs are parsed with PyMuPDF in `extract_pdf_text()`
- DOCX files are parsed with `python-docx` in `extract_docx_text()`
- text is normalized with `sanitize_text()`
- if too little readable text is found, the task fails with an extraction error

### 8. AI Provider Selection and Analysis

The extracted text is sent to an analysis provider, which returns structured JSON.

Responsible Python files:

- [analyzer/services/ai.py](/d:/django-projects/analyzer/services/ai.py)
- [core/settings.py](/d:/django-projects/core/settings.py)

Provider-related classes and functions:

- `AnalysisInput`
- `BaseAnalysisProvider`
- `PlaceholderAnalysisProvider`
- `GeminiAnalysisProvider`
- `get_analysis_provider()`

What happens:

- `get_analysis_provider()` reads `RESUMEIQ_ANALYSIS_PROVIDER`
- `PlaceholderAnalysisProvider` returns deterministic mock analysis for local/demo use
- `GeminiAnalysisProvider` sends the prompt to Gemini and expects structured JSON back
- `validate_analysis()` ensures required fields are present and normalized before saving

Important settings involved:

- `ANALYSIS_PROVIDER`
- `GEMINI_API_KEY`
- `GEMINI_MODEL_ID`
- `USE_THREAD_QUEUE_FALLBACK`
- `CELERY_*`

### 9. Polling and Result Display

After submission, the user is redirected to a waiting screen while the app polls for task completion.

Responsible Python files:

- [analyzer/views.py](/d:/django-projects/analyzer/views.py)
- [analyzer/models.py](/d:/django-projects/analyzer/models.py)

Views involved:

- `AnalyzingView`
- `ResultStatusView`
- `ResultsView`
- `SharedResultsView`
- `GenerateShareLinkView`
- `ErrorView`

What happens:

- `AnalyzingView` renders the intermediate page
- `ResultStatusView` returns status HTML for polling
- once complete, the user is redirected to the results page
- `ResultsView` renders the owner view
- `SharedResultsView` renders the public share page if sharing is enabled
- `GenerateShareLinkView` turns on share access and returns a shareable URL

### 10. Admin Access

The stored results and request logs are visible in Django admin.

Responsible Python files:

- [analyzer/admin.py](/d:/django-projects/analyzer/admin.py)

What happens:

- `AnalysisResultAdmin` exposes searchable/filterable result records
- `AnalysisRequestLogAdmin` exposes request-log records

### 11. App Configuration and Global Settings

Global project configuration lives in the Django settings module.

Responsible Python files:

- [core/settings.py](/d:/django-projects/core/settings.py)
- [analyzer/apps.py](/d:/django-projects/analyzer/apps.py)

What `core/settings.py` controls:

- database selection
- static and media paths
- upload size limits
- retention settings
- rate limiting settings
- provider configuration
- Celery configuration
- logging configuration

## Process-to-File Map

### Upload and Validation

- [analyzer/views.py](/d:/django-projects/analyzer/views.py)
- [analyzer/forms.py](/d:/django-projects/analyzer/forms.py)
- [analyzer/services/security.py](/d:/django-projects/analyzer/services/security.py)

### Data Storage

- [analyzer/models.py](/d:/django-projects/analyzer/models.py)
- [analyzer/migrations/0001_initial.py](/d:/django-projects/analyzer/migrations/0001_initial.py)

### Queueing and Background Work

- [analyzer/services/queue.py](/d:/django-projects/analyzer/services/queue.py)
- [analyzer/tasks.py](/d:/django-projects/analyzer/tasks.py)
- [core/celery.py](/d:/django-projects/core/celery.py)
- [core/__init__.py](/d:/django-projects/core/__init__.py)

### Text Extraction

- [analyzer/services/extraction.py](/d:/django-projects/analyzer/services/extraction.py)

### AI Analysis

- [analyzer/services/ai.py](/d:/django-projects/analyzer/services/ai.py)
- [core/settings.py](/d:/django-projects/core/settings.py)

### Results and Sharing

- [analyzer/views.py](/d:/django-projects/analyzer/views.py)
- [analyzer/models.py](/d:/django-projects/analyzer/models.py)

### Admin and Monitoring

- [analyzer/admin.py](/d:/django-projects/analyzer/admin.py)
- [core/settings.py](/d:/django-projects/core/settings.py)

## Debugging Guide

When something goes wrong, these files are usually the first places to inspect:

- Upload rejected: [analyzer/forms.py](/d:/django-projects/analyzer/forms.py), [analyzer/services/security.py](/d:/django-projects/analyzer/services/security.py)
- Missing tables or schema issues: [analyzer/migrations/0001_initial.py](/d:/django-projects/analyzer/migrations/0001_initial.py), [core/settings.py](/d:/django-projects/core/settings.py)
- Queue/Celery issues: [analyzer/services/queue.py](/d:/django-projects/analyzer/services/queue.py), [analyzer/tasks.py](/d:/django-projects/analyzer/tasks.py), [core/celery.py](/d:/django-projects/core/celery.py)
- PDF or DOCX parsing problems: [analyzer/services/extraction.py](/d:/django-projects/analyzer/services/extraction.py)
- AI provider failures: [analyzer/services/ai.py](/d:/django-projects/analyzer/services/ai.py), [logs/resumeiq-errors.log](/d:/django-projects/logs/resumeiq-errors.log)
- Result rendering or polling issues: [analyzer/views.py](/d:/django-projects/analyzer/views.py), [analyzer/urls.py](/d:/django-projects/analyzer/urls.py)

## Python File Inventory

### Project Core

- [core/settings.py](/d:/django-projects/core/settings.py)
- [core/urls.py](/d:/django-projects/core/urls.py)
- [core/asgi.py](/d:/django-projects/core/asgi.py)
- [core/wsgi.py](/d:/django-projects/core/wsgi.py)
- [core/celery.py](/d:/django-projects/core/celery.py)
- [core/__init__.py](/d:/django-projects/core/__init__.py)

### Analyzer App

- [analyzer/apps.py](/d:/django-projects/analyzer/apps.py)
- [analyzer/admin.py](/d:/django-projects/analyzer/admin.py)
- [analyzer/forms.py](/d:/django-projects/analyzer/forms.py)
- [analyzer/models.py](/d:/django-projects/analyzer/models.py)
- [analyzer/tasks.py](/d:/django-projects/analyzer/tasks.py)
- [analyzer/urls.py](/d:/django-projects/analyzer/urls.py)
- [analyzer/views.py](/d:/django-projects/analyzer/views.py)
- [analyzer/context_processors.py](/d:/django-projects/analyzer/context_processors.py)
- [analyzer/services/ai.py](/d:/django-projects/analyzer/services/ai.py)
- [analyzer/services/extraction.py](/d:/django-projects/analyzer/services/extraction.py)
- [analyzer/services/queue.py](/d:/django-projects/analyzer/services/queue.py)
- [analyzer/services/security.py](/d:/django-projects/analyzer/services/security.py)

### Tests

- [analyzer/tests/test_ai.py](/d:/django-projects/analyzer/tests/test_ai.py)
- [analyzer/tests/test_extraction.py](/d:/django-projects/analyzer/tests/test_extraction.py)
- [analyzer/tests/test_models.py](/d:/django-projects/analyzer/tests/test_models.py)
- [analyzer/tests/test_views.py](/d:/django-projects/analyzer/tests/test_views.py)

## Short Summary

If you want the shortest mental model of the app, it is:

- `views.py` handles web requests
- `forms.py` and `security.py` validate uploads
- `models.py` stores analysis jobs and logs
- `queue.py` and `tasks.py` run the analysis asynchronously
- `extraction.py` reads PDF or DOCX text
- `ai.py` talks to the provider and normalizes the result
- `settings.py` controls the runtime behavior
