import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from core.models import AuditQuerySet
from core.workflow_models import WorkflowQuerySet


class ManagedQuerySet(WorkflowQuerySet):
    def delete(self):
        raise ValidationError("Operational records are retained; archive them instead.")


class ManagedRecord(models.Model):
    objects = ManagedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not getattr(self, "_operations_write", False):
            raise ValidationError("Use operations services to save this record.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Operational records are retained; archive them instead.")


class BusinessSettings(ManagedRecord):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    local_currency = models.CharField(max_length=3, choices=[("UGX", "UGX"), ("USD", "USD")], default="UGX")
    international_currency = models.CharField(max_length=3, choices=[("UGX", "UGX"), ("USD", "USD")], default="USD")
    ugx_approval_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=50000000)
    usd_approval_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=15000)
    notify_quotations = models.BooleanField(default=True)
    notify_enquiries = models.BooleanField(default=True)
    notify_overdue = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=0, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, editable=False)

    class Meta:
        default_permissions = ("view", "change")
        permissions = [("view_reports", "Can view operational reports"), ("export_reports", "Can export operational reports")]
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="business_settings_singleton"),
            models.CheckConstraint(condition=models.Q(ugx_approval_threshold__gte=0, usd_approval_threshold__gte=0), name="settings_nonnegative_thresholds"),
            models.CheckConstraint(condition=models.Q(local_currency__in=["UGX", "USD"], international_currency__in=["UGX", "USD"]) & ~models.Q(local_currency=models.F("international_currency")), name="settings_supported_currencies"),
        ]

    def clean(self):
        if self.local_currency == self.international_currency:
            raise ValidationError("Local and international currencies must differ.")


class InventoryItem(ManagedRecord):
    sku = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    warehouse = models.ForeignKey("organization.Warehouse", on_delete=models.PROTECT, related_name="inventory_items")
    unit = models.CharField(max_length=20, default="units")
    quantity = models.DecimalField(max_digits=15, decimal_places=3, default=0, editable=False)
    reorder_level = models.DecimalField(max_digits=15, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["sku", "pk"]
        permissions = [("adjust_inventory", "Can receive and issue warehouse stock")]
        constraints = [
            models.UniqueConstraint(fields=["sku", "warehouse"], name="unique_warehouse_sku"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0, reorder_level__gte=0), name="inventory_nonnegative_values"),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"


class StockMovement(ManagedRecord):
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="movements")
    quantity_change = models.DecimalField(max_digits=15, decimal_places=3)
    balance_after = models.DecimalField(max_digits=15, decimal_places=3)
    reason = models.CharField(max_length=255)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)
        constraints = [models.CheckConstraint(condition=~models.Q(quantity_change=0) & models.Q(balance_after__gte=0), name="movement_nonzero_and_nonnegative_balance")]


class DeliveryProof(ManagedRecord):
    shipment = models.OneToOneField("shipments.Shipment", on_delete=models.PROTECT, related_name="delivery_proof")
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    recipient_name = models.CharField(max_length=200)
    delivered_at = models.DateTimeField()
    notes = models.TextField(blank=True, max_length=4000)
    # Evidence bytes are private, transactionally stored, never exposed through MEDIA_URL.
    evidence = models.BinaryField(editable=False)
    evidence_name = models.CharField(max_length=100)
    evidence_type = models.CharField(max_length=50)
    evidence_sha256 = models.CharField(max_length=64, editable=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ("view", "add")


class OperationsEvent(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    actor_label = models.CharField(max_length=150)
    entity_type = models.CharField(max_length=40)
    entity_id = models.CharField(max_length=100)
    action = models.CharField(max_length=50)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Operations events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Operations events are append-only.")
