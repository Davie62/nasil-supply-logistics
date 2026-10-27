"""Shared numeric, approval and audit rules for commercial apps."""
import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from core.business_rules import decimal_value, approval_limit, require_permission
from .models import ManagedRecord
from .services import managed_save, event, require_admin


class CommercialRecord(ManagedRecord):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-pk"]

    def __str__(self):
        return str(getattr(self, "number", None) or getattr(self, "name", None) or self.reference)


def money(value, positive=True):
    value = decimal_value(value, "Amount", Decimal("0.01") if positive else Decimal("0"))
    if value != value.quantize(Decimal("0.01")) or value > Decimal("9999999999999.99"):
        raise ValidationError("Amounts support up to two decimals and 13 integer digits.")
    return value


def quantity(value):
    value = decimal_value(value, "Quantity", Decimal("0.001"))
    if value != value.quantize(Decimal("0.001")) or value > Decimal("999999999999.999"):
        raise ValidationError("Quantities support up to three decimals.")
    return value


def approve(actor, record, permission, amount, currency):
    require_permission(actor, permission)
    if actor.pk == record.created_by_id:
        raise ValidationError("The preparer cannot approve their own record.")
    money(amount)
    require_admin(actor)


def persist(record, actor, action, **details):
    def snapshot(value):
        return {field.attname: str(getattr(value, field.attname)) for field in value._meta.concrete_fields if field.name not in {"payload"}}
    previous = record.__class__.objects.filter(pk=record.pk).first() if record.pk and not record._state.adding else None
    record.version += 1
    record.full_clean()
    managed_save(record)
    event(actor, record._meta.model_name, record.pk, action, reference=str(record.reference), before=snapshot(previous) if previous else {}, after=snapshot(record), **details)
    return record


def editable_data(data, allowed):
    if set(data) - set(allowed):
        raise ValidationError("Unsupported fields; use the appropriate workflow action.")


def number(prefix):
    return prefix + "-" + uuid.uuid4().hex[:16].upper()
