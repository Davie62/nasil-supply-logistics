from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import AuditRecord
from payments.models import Invoice
from .notifications import enqueue_event, enqueue_invoice


@receiver(post_save, sender=AuditRecord)
def notify_business_event(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        enqueue_event(instance)


@receiver(post_save, sender=Invoice)
def notify_invoice(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        enqueue_invoice(instance)
