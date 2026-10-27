from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import AuditRecord
from operations.commercial import persist
from .models import Order

@receiver(post_save, sender=AuditRecord)
def synchronize_order_dispatch(sender, instance, created, raw=False, **kwargs):
    if raw or not created or not instance.shipment_id or instance.to_status != "in_transit" or instance.action != "status_changed":
        return
    order = Order.objects.select_for_update().filter(shipment_id=instance.shipment_id, status="fulfilled").first()
    if order:
        order.status = "shipped"
        persist(order, instance.actor, "order_dispatched", shipment=instance.shipment.tracking_number)
