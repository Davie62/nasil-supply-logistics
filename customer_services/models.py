import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class CustomerAccess(models.Model):
    customer = models.OneToOneField("customers.Customer", on_delete=models.PROTECT, related_name="portal_access")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_access")
    verified_email = models.EmailField()
    enabled = models.BooleanField(default=True)
    verified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("view",)
        permissions = [("manage_access", "Can invite and revoke customer portal access")]


class RegistrationVerification(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="registration_verification")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    code_hash = models.CharField(max_length=128)
    generation = models.UUIDField(default=uuid.uuid4)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()


class PortalInvitation(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="portal_invitations")
    email = models.EmailField()
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ("view",)


class NotificationPreference(models.Model):
    customer = models.OneToOneField("customers.Customer", on_delete=models.PROTECT, related_name="notification_preference")
    preferred_channel = models.CharField(max_length=10, choices=[("email", "Email"), ("sms", "SMS")], default="email")
    sms_number = models.CharField(max_length=16, blank=True)
    sms_consent = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    quotation_updates = models.BooleanField(default=True)
    shipment_updates = models.BooleanField(default=True)
    delivery_updates = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("view",)
        constraints = [models.CheckConstraint(condition=models.Q(preferred_channel__in=["email", "sms"]), name="customer_valid_channel")]


class CustomerNotification(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="notifications")
    audit = models.ForeignKey("core.AuditRecord", on_delete=models.PROTECT, null=True, blank=True)
    invitation = models.ForeignKey(PortalInvitation, on_delete=models.PROTECT, null=True, blank=True)
    event_key = models.CharField(max_length=120, unique=True)
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    body = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict)
    channel = models.CharField(max_length=10, default="email")
    recipient = models.CharField(max_length=254, blank=True)
    status = models.CharField(max_length=20, choices=[("queued", "Queued"), ("processing", "Processing"), ("sent", "Provider accepted"), ("failed", "Retry pending"), ("suppressed", "Not sent"), ("exhausted", "Delivery failed")], default="queued", db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=100, blank=True)
    provider = models.CharField(max_length=30, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)
        indexes = [models.Index(fields=["status", "next_attempt_at"])]


class DeliveryAttempt(models.Model):
    notification = models.ForeignKey(CustomerNotification, on_delete=models.PROTECT, related_name="delivery_attempts")
    provider = models.CharField(max_length=30)
    accepted = models.BooleanField(default=False)
    error_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ("view",)


class RateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        default_permissions = ()
