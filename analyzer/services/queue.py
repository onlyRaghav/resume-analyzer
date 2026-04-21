import logging
import threading

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def queue_analysis_job(result_id: int):
    try:
        from analyzer.tasks import run_analysis

        if hasattr(run_analysis, "delay") and not settings.CELERY_TASK_ALWAYS_EAGER:
            run_analysis.delay(result_id)
            return
        run_analysis(result_id)
        return
    except Exception as exc:
        logger.warning("Falling back from Celery dispatch to thread queue: %s", exc)

    if not settings.RESUMEIQ_USE_THREAD_FALLBACK:
        raise

    def worker():
        close_old_connections()
        from analyzer.tasks import run_analysis

        run_analysis(result_id)

    thread = threading.Thread(target=worker, daemon=True, name=f"analysis-{result_id}")
    thread.start()
