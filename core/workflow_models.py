"""Protect normal ORM writes from accidentally bypassing workflow services."""
from django.core.exceptions import ValidationError
from django.db import models, transaction


class WorkflowQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Use workflow functions to update business records.")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError("Bulk creation bypasses workflow validation and auditing.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Use workflow functions to update business records.")


class WorkflowModel(models.Model):
    objects = WorkflowQuerySet.as_manager()
    version = models.PositiveIntegerField(default=0, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not getattr(self, "_workflow_write", False):
            if not self._state.adding or self._meta.label_lower == "shipments.shipment" or self.status != "pending":
                raise ValidationError("Use workflow functions to save this record.")
            if self.approved_by_id or self.approved_at or self.created_by_id or self.prepared_by_id:
                raise ValidationError("Approval and staff attribution require the workflow.")
            if any(getattr(self, field) for field in ("base_amount", "rate_per_kg", "surcharge", "discount", "tax_rate")):
                raise ValidationError("Staff must prepare pricing through the quotation workflow.")
        self.full_clean()
        with transaction.atomic(using=kwargs.get("using") or self._state.db or "default"):
            return super().save(*args, **kwargs)


def workflow_save(instance, actor, action, reason=""):
    instance._workflow_write = True
    instance._audit_actor = actor
    instance._audit_action = action
    instance._audit_reason = reason
    instance.version += 1
    try:
        instance.save()
    finally:
        for attribute in ("_workflow_write", "_audit_actor", "_audit_action", "_audit_reason"):
            instance.__dict__.pop(attribute, None)
