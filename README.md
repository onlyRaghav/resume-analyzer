# ResumeIQ

ResumeIQ is a Django-based resume analyzer MVP built from the attached PRD. It supports PDF or DOCX upload, text extraction, Gemini-backed AI analysis, async-style processing, and shareable read-only result pages.

## Stack

- Django application with server-rendered templates
- SQLite by default, PostgreSQL-ready via `DATABASE_URL`
- Celery and Redis wiring with a thread fallback for local development
- PyMuPDF and `python-docx` for resume extraction
- HTMX-enhanced status polling

## Local Setup

1. Create a virtual environment and activate it.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and adjust values if needed.
4. Run `python manage.py migrate`.
5. Start the app with `python manage.py runserver`.

## Docker Setup

1. Ensure Docker is installed.
2. Ensure Docker Desktop is running and your terminal has permission to access the Docker daemon.
3. Run `docker compose up --build`.
4. Visit `http://localhost:8000`.

The `web` service now runs `python manage.py migrate` automatically before starting Django, so the PostgreSQL schema is created on startup.

## Render Deployment

1. Push this repo to GitHub.
2. In Render, create a new Blueprint and point it at the repo.
3. Render will read [render.yaml](/d:/django-projects/render.yaml) and provision:
   - a web service named `resumeiq-web`
   - a PostgreSQL database named `resumeiq-db`
4. After the first deploy completes, open the generated Render URL.

What the Render setup does:

- installs dependencies with `pip install -r requirements.txt`
- runs `python manage.py collectstatic --noinput` during build
- runs `python manage.py migrate` before starting `gunicorn`
- uses `ANALYSIS_PROVIDER=placeholder` by default for a stable first deployment
- serves static assets in production via WhiteNoise

## Notes

- `ANALYSIS_PROVIDER=placeholder` is the current safest default and uses the built-in heuristic analyzer.
- `GEMINI_API_KEY` and `GEMINI_MODEL_ID` are still available for the live Gemini integration when you want to revisit it.
- `MIN_ANALYSIS_DISPLAY_SECONDS` controls the minimum time the analyzing screen stays visible before redirecting to results.
- If Celery is not installed or unavailable locally, analysis jobs fall back to an in-process background thread so the demo flow still works.
- PDF extraction requires `PyMuPDF`, and server-side MIME sniffing requires `python-magic`.
