import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from core.models import AuditQuerySet


class MFAProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_profile")
    encrypted_secret = models.TextField(blank=True)
    enabled = models.BooleanField(default=False)
    last_counter = models.BigIntegerField(default=-1)
    recovery_hashes = models.JSONField(default=list)
    session_version = models.PositiveIntegerField(default=1)
    revocation_version = models.PositiveIntegerField(default=1)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()


class SecurityEvent(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.CharField(max_length=60, db_index=True)
    level = models.CharField(max_length=10)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    target_id = models.PositiveBigIntegerField(null=True)
    ip_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    request_id = models.CharField(max_length=36, blank=True)
    route = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Security events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Security events are retained.")


class SecurityAlert(models.Model):
    fingerprint = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=60)
    event = models.ForeignKey(SecurityEvent, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)
