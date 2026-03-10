# Import Celery app so it is loaded when Django starts (enables autodiscover).
from .celery import app as celery_app

__all__ = ("celery_app",)
