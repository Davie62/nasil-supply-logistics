from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from core.workflow_models import WorkflowModel
from core.business_rules import calculate_price
import uuid

class Quote(WorkflowModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    quote_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='quotes')
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
    trade_type = models.CharField(max_length=20, choices=[("local", "Local"), ("international", "International")], default="local")
    currency = models.CharField(max_length=3, default="UGX", editable=False)
    base_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    rate_per_kg = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    surcharge = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    valid_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="prepared_quotes", editable=False)
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="priced_quotes", editable=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_quotes", editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        permissions = [("approve_quote", "Can approve quotations"), ("approve_high_value_quote", "Can approve quotations above the configured threshold")]
        constraints = [
            models.CheckConstraint(condition=models.Q(trade_type__in=["local", "international"], currency__in=["UGX", "USD"]), name="quote_supported_trade_currency"),
            models.CheckConstraint(condition=models.Q(weight__gt=0), name="quote_positive_weight"),
            models.CheckConstraint(condition=models.Q(cargo_value__isnull=True) | models.Q(cargo_value__gte=0), name="quote_nonnegative_cargo_value"),
            models.CheckConstraint(condition=models.Q(base_amount__gte=0, rate_per_kg__gte=0, surcharge__gte=0, discount__gte=0, subtotal__gte=0, tax_amount__gte=0, total_amount__gte=0, tax_rate__gte=0, tax_rate__lte=100), name="quote_valid_pricing"),
            models.CheckConstraint(condition=models.Q(status__in=["pending", "reviewed", "approved", "rejected"]), name="quote_valid_status"),
        ]

    def clean(self):
        super().clean()
        from operations.policy import currency_for_scope
        previous = type(self).objects.filter(pk=self.pk).values("trade_type", "currency").first() if self.pk else None
        self.currency = previous["currency"] if previous and previous["trade_type"] == self.trade_type else currency_for_scope(self.trade_type)
        if not self.currency:
            raise ValidationError({"trade_type": "Choose local or international."})
        self.subtotal, self.tax_amount, self.total_amount = calculate_price(
            weight=self.weight, base_amount=self.base_amount, rate_per_kg=self.rate_per_kg,
            surcharge=self.surcharge, discount=self.discount, tax_rate=self.tax_rate,
        )

    def save(self, *args, **kwargs):
        if not self.quote_number:
            self.quote_number = f"QT-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quote_number} - {self.customer.full_name}"
