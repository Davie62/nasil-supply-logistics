import uuid
from django.conf import settings
from django.db import models
from operations.models import ManagedRecord


class Invoice(ManagedRecord):
    def __str__(self):
        return self.number

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField(max_length=40, unique=True)
    quote = models.OneToOneField("quotations.Quote", on_delete=models.PROTECT, related_name="invoice")
    currency = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    pricing = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=[("issued", "Issued"), ("void", "Void")], default="issued")
    due_date = models.DateField()
    customer_note = models.TextField(blank=True, max_length=2000)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0, currency__in=["UGX", "USD"], status__in=["issued", "void"]), name="invoice_valid_amount_currency_status")]
