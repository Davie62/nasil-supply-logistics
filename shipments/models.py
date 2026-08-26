from django.db import models
import uuid

class Shipment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )

    tracking_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)
    quote = models.OneToOneField('quotations.Quote', on_delete=models.CASCADE, related_name='shipment')
    carrier = models.ForeignKey('logistics.Carrier', on_delete=models.SET_NULL, null=True, blank=True, related_name='shipments')
    current_location = models.CharField(max_length=255, blank=True, null=True)
    estimated_delivery = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            self.tracking_number = f"TRK-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tracking_number} - {self.status}"
