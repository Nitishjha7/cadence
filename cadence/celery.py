import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cadence.settings")

app = Celery("cadence")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
