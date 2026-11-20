import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

try:
    from celery import Celery
except ModuleNotFoundError:
    app = None
else:
    app = Celery("nasil")
    app.config_from_object("django.conf:settings", namespace="CELERY")
    app.autodiscover_tasks()
