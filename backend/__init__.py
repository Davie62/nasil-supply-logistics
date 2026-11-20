try:
    from .celery import app as celery_app
except Exception:  # Celery is optional for core Django commands when not installed/configured.
    celery_app = None

__all__ = ("celery_app",)
