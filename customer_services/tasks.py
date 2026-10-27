import uuid
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from .models import CustomerNotification, DeliveryAttempt
from .notifications import recipient_for, render_delivery
from . import providers

MAX_ATTEMPTS = 5


def due_notifications():
    now = timezone.now()
    return CustomerNotification.objects.filter(attempts__lt=MAX_ATTEMPTS).filter(
        Q(status__in=["queued", "failed"], next_attempt_at__lte=now) | Q(status="processing", lease_until__lt=now))


@transaction.atomic
def claim(notification_id):
    queryset = due_notifications().filter(pk=notification_id)
    queryset = queryset.select_for_update(skip_locked=True) if connection.features.has_select_for_update_skip_locked else queryset.select_for_update()
    notification = queryset.first()
    if not notification:
        return None
    notification.status, notification.lease_token = "processing", uuid.uuid4()
    notification.lease_until = timezone.now() + timedelta(minutes=5)
    notification.attempts += 1
    notification.save(update_fields=["status", "lease_token", "lease_until", "attempts"])
    return notification


def allowed_to_deliver(notification):
    if notification.kind == "registration_verification":
        from .registration import verification_delivery_allowed
        return verification_delivery_allowed(notification)
    if notification.kind == "invitation":
        invitation = notification.invitation
        return not invitation.revoked_at and not invitation.accepted_at and invitation.expires_at > timezone.now() and invitation.email.lower() == invitation.customer.email.lower()
    channel, recipient, suppression = recipient_for(notification.customer, notification.kind)
    return not suppression and channel == notification.channel and recipient == notification.recipient


@shared_task(bind=True, max_retries=MAX_ATTEMPTS, acks_late=True, reject_on_worker_lost=True)
def deliver_notification(self, notification_id):
    if not settings.NOTIFICATIONS_DELIVERY_ENABLED:
        return "disabled"
    notification = claim(notification_id)
    if not notification:
        return "not_due"
    owned = CustomerNotification.objects.filter(pk=notification.pk, lease_token=notification.lease_token, status="processing")
    if not allowed_to_deliver(notification):
        owned.update(status="suppressed", last_error="preferences_or_access_changed", lease_until=None)
        return "suppressed"
    text, html, sms = render_delivery(notification)
    attempts = [("sendgrid", lambda: providers.sendgrid(notification, text, html))] if notification.channel == "email" else [
        ("twilio", lambda: providers.twilio(notification, sms)), ("africastalking", lambda: providers.africastalking(notification, sms))]
    last_error = providers.ProviderError("no_provider")
    retryable = False
    for name, send in attempts:
        try:
            message_id = send()
        except providers.ProviderError as error:
            last_error = error
            retryable = retryable or error.retryable
            DeliveryAttempt.objects.create(notification=notification, provider=name, error_code=error.code)
            if not error.fallback:
                break
        else:
            DeliveryAttempt.objects.create(notification=notification, provider=name, accepted=True)
            owned.update(status="sent", sent_at=timezone.now(), provider=name, provider_message_id=message_id, last_error="", lease_until=None)
            if notification.kind == "registration_verification":
                CustomerNotification.objects.filter(pk=notification.pk, lease_token=notification.lease_token).update(payload={})
            return "sent"
    exhausted = not retryable or notification.attempts >= MAX_ATTEMPTS
    delay = min(3600, 60 * (2 ** (notification.attempts - 1)))
    owned.update(status="exhausted" if exhausted else "failed", last_error=last_error.code, next_attempt_at=timezone.now() + timedelta(seconds=delay), lease_until=None)
    if not exhausted:
        raise self.retry(countdown=delay, exc=RuntimeError("Notification provider temporarily unavailable"))
    return "exhausted"


@shared_task
def dispatch_due():
    if not settings.NOTIFICATIONS_DELIVERY_ENABLED:
        return 0
    CustomerNotification.objects.filter(status="processing", lease_until__lt=timezone.now(), attempts__gte=MAX_ATTEMPTS).update(status="exhausted", last_error="worker_lease_expired")
    identifiers = list(due_notifications().order_by("next_attempt_at").values_list("pk", flat=True)[:100])
    for identifier in identifiers:
        deliver_notification.delay(identifier)
    return len(identifiers)
