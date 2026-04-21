from django.conf import settings


def product_context(_request):
    return {
        "PRODUCT_NAME": settings.RESUMEIQ_PRODUCT_NAME,
        "PRIVACY_NOTICE": settings.RESUMEIQ_PRIVACY_NOTICE,
        "MAX_JOB_DESCRIPTION_CHARS": settings.RESUMEIQ_MAX_JOB_DESCRIPTION_CHARS,
    }
