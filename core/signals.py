"""Synchronous audit writes roll back with the enclosing business transaction."""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from quotations.models import Quote
from shipments.models import Shipment
from .models import AuditRecord


def snapshot(instance):
    return {field.attname: str(getattr(instance, field.attname)) if getattr(instance, field.attname) is not None else None
            for field in instance._meta.concrete_fields}


@receiver(pre_save, sender=Quote)
@receiver(pre_save, sender=Shipment)
def capture_previous(sender, instance, raw=False, using="default", **kwargs):
    if raw:
        return
    previous = sender.objects.using(using).filter(pk=instance.pk).first() if instance.pk else None
    instance._audit_before = snapshot(previous) if previous else {}


@receiver(post_save, sender=Quote)
@receiver(post_save, sender=Shipment)
def record_business_change(sender, instance, created, raw=False, using="default", **kwargs):
    if raw:
        return
    before = instance.__dict__.pop("_audit_before", {})
    after = snapshot(instance)
    changes = {key: {"before": before.get(key), "after": value} for key, value in after.items() if before.get(key) != value}
    actor = getattr(instance, "_audit_actor", None)
    AuditRecord.objects.using(using).create(
        quote_id=instance.pk if sender is Quote else instance.quote_id,
        shipment_id=instance.pk if sender is Shipment else None,
        actor=actor, actor_label=actor.get_username() if actor else "Public / system",
        action=getattr(instance, "_audit_action", "created" if created else "updated"),
        from_status=before.get("status") or "", to_status=instance.status,
        reason=getattr(instance, "_audit_reason", ""), changes=changes,
        object_version=instance.version,
    )
