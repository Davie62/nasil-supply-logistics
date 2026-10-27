from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from customer_services.tasks import dispatch_due, due_notifications


class Command(BaseCommand):
    help = "Show pending outbox count, or publish due notifications to Celery with --publish."

    def add_arguments(self, parser):
        parser.add_argument("--publish", action="store_true")

    def handle(self, *args, **options):
        if options["publish"]:
            if not settings.NOTIFICATIONS_DELIVERY_ENABLED:
                raise CommandError("Enable notifications and configure the broker/providers before publishing.")
            self.stdout.write(f"Published {dispatch_due()} due notifications.")
        else:
            self.stdout.write(f"Due notifications: {due_notifications().count()}. No messages sent or published.")
