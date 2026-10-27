from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from customer_services.models import CustomerNotification, DeliveryAttempt
from customer_services.notifications import schedule


class Command(BaseCommand):
    help = "Explicitly requeue a failed/exhausted notification after fixing provider configuration."

    def add_arguments(self, parser):
        parser.add_argument("reference")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            notification = CustomerNotification.objects.select_for_update().get(reference=options["reference"])
        except (CustomerNotification.DoesNotExist, ValueError, ValidationError):
            raise CommandError("Notification not found.")
        if notification.status not in {"failed", "exhausted"}:
            raise CommandError("Only failed or exhausted notifications can be requeued.")
        DeliveryAttempt.objects.create(notification=notification, provider="operator", error_code="manual_requeue")
        notification.status, notification.attempts, notification.last_error = "queued", 0, ""
        notification.next_attempt_at, notification.lease_until, notification.lease_token = timezone.now(), None, None
        notification.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "lease_until", "lease_token"])
        schedule(notification)
        self.stdout.write(f"Requeued notification {notification.reference}; access/preferences will be checked again.")
