import uuid

from .managers import ActiveManager, AllObjectsManager
from django.conf import settings
from django.db import models
from django.utils import timezone



class BaseModel(models.Model):
    objects = ActiveManager()
    all_objects = AllObjectsManager()
    """
    Enterprise base model inherited by every model
    in the system.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
    )

    is_active = models.BooleanField(
        default=True
    )

    is_deleted = models.BooleanField(
        default=False
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        abstract = True

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])

class ContactMessage(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.subject} - {self.name}"


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("Audit records are append-only.")

    def delete(self):
        raise ValueError("Audit records are append-only.")

    def bulk_update(self, *args, **kwargs):
        raise ValueError("Audit records are append-only.")


class AuditRecord(models.Model):
    """Business change history; linked records cannot be deleted underneath it."""
    quote = models.ForeignKey("quotations.Quote", on_delete=models.PROTECT, null=True, blank=True, related_name="audit_records")
    shipment = models.ForeignKey("shipments.Shipment", on_delete=models.PROTECT, null=True, blank=True, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_label = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=40)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    changes = models.JSONField(default=dict)
    object_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)
        constraints = [models.CheckConstraint(condition=models.Q(quote__isnull=False) | models.Q(shipment__isnull=False), name="audit_has_business_record")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Audit records are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit records are append-only.")
