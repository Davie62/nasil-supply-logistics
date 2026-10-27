from django.apps import AppConfig


class CustomerServicesConfig(AppConfig):
    name = "customer_services"

    def ready(self):
        from . import signals  # noqa: F401
