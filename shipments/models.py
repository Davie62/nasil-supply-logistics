from django.db import models
from django.conf import settings
from core.workflow_models import WorkflowModel
import uuid

class Shipment(WorkflowModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )

    tracking_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)
    quote = models.OneToOneField('quotations.Quote', on_delete=models.PROTECT, related_name='shipment')
    carrier = models.ForeignKey('logistics.Carrier', on_delete=models.SET_NULL, null=True, blank=True, related_name='shipments')
    current_location = models.CharField(max_length=255, blank=True, null=True)
    estimated_delivery = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True, editable=False)
    delivered_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_shipments", editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["pending", "in_transit", "delivered", "cancelled"]), name="shipment_valid_status")]

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            self.tracking_number = f"TRK-{uuid.uuid4().hex.upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tracking_number} - {self.status}"
