from django.apps import AppConfig


class SecurityControlsConfig(AppConfig):
    name = "security_controls"
    verbose_name = "Security monitoring"

    def ready(self):
        from . import signals  # noqa: F401
