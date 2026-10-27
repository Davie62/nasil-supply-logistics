from django.db.models.signals import post_save
from django.dispatch import receiver
from payments.models import Invoice
from operations.models import OperationsEvent
from .models import Connection
from .services import enqueue, invoice_snapshot, purchase_snapshot

@receiver(post_save, sender=Invoice)
def invoice_accounting_export(sender, instance, created, raw=False, **kwargs):
    if raw or not created or not instance.issued_by_id:
        return
    for connection in Connection.objects.filter(code="odoo", is_active=True):
        enqueue(actor=instance.issued_by, connection=connection, operation="invoice", event_key=f"odoo:invoice:{instance.reference}", payload=invoice_snapshot(instance))

@receiver(post_save, sender=OperationsEvent)
def purchase_accounting_export(sender, instance, created, raw=False, **kwargs):
    if raw or not created:
        return
    if instance.entity_type == "invoice" and instance.action == "invoice_voided":
        document = Invoice.objects.get(pk=instance.entity_id)
        operation, payload = "invoice_void", invoice_snapshot(document)
    elif instance.entity_type == "purchaseorder" and instance.action == "purchase_transition" and instance.details.get("target") in {"approved", "cancelled"}:
        from procurement.models import PurchaseOrder
        document = PurchaseOrder.objects.get(pk=instance.entity_id)
        operation = "purchase_order" if instance.details["target"] == "approved" else "purchase_void"
        payload = purchase_snapshot(document)
    else:
        return
    for connection in Connection.objects.filter(code="odoo", is_active=True):
        enqueue(actor=instance.actor, connection=connection, operation=operation, event_key=f"odoo:{operation}:{document.reference}", payload=payload)
