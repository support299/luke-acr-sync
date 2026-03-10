"""
Celery configuration for acr_sync project.
Discovers tasks from all INSTALLED_APPS (looks for tasks.py in each app).
"""
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module so Celery can find it.
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "acr_sync.settings")

app = Celery("acr_sync")

# Load config from Django settings with the CELERY namespace.
# All Celery-related settings should be prefixed with CELERY_ in settings.py.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps (looks for tasks.py in each app).
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Optional: simple task to verify Celery is working."""
    print(f"Request: {self.request!r}")
