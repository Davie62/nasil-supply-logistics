from django.db import models
import uuid

class Quote(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    quote_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='quotes')
    service = models.ForeignKey('logistics.Service', on_delete=models.SET_NULL, null=True, blank=True, related_name='quotes')
    pickup_location = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    transport_mode = models.CharField(max_length=100, blank=True, null=True)
    cargo_description = models.TextField()
    weight = models.DecimalField(max_digits=10, decimal_places=2, help_text="Weight in kg")
    cargo_value = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.quote_number:
            self.quote_number = f"QT-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quote_number} - {self.customer.full_name}"
