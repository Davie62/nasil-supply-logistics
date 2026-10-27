from django.conf import settings
from django.db import models
from operations.commercial import CommercialRecord
from payments.models import Invoice as ExistingInvoice


class Invoice(ExistingInvoice):
    """Canonical existing invoice rows, exposed through the finance app."""
    class Meta:
        proxy = True


class Payment(CommercialRecord):
    def __str__(self):
        return f"{self.external_reference} / {self.currency} {self.amount} / {self.status}"

    invoice = models.ForeignKey("payments.Invoice", on_delete=models.PROTECT, null=True, blank=True, related_name="finance_payments")
    purchase_order = models.ForeignKey("procurement.PurchaseOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, choices=[("UGX", "UGX"), ("USD", "USD")])
    method = models.CharField(max_length=10, choices=[("bank", "Bank"), ("cash", "Cash"), ("gateway", "Gateway")])
    external_reference = models.CharField(max_length=150)
    provider = models.CharField(max_length=60, default="manual")
    idempotency_key = models.CharField(max_length=150, unique=True)
    paid_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=[("posted", "Posted"), ("reversed", "Reversed")], default="posted")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reversal_reason = models.CharField(max_length=255, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta(CommercialRecord.Meta):
        permissions = [("reverse_payment", "Can reverse an unreconciled payment")]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0, currency__in=["UGX", "USD"]), name="finance_positive_payment"),
            models.CheckConstraint(condition=(models.Q(invoice__isnull=False, purchase_order__isnull=True) | models.Q(invoice__isnull=True, purchase_order__isnull=False)), name="payment_one_document"),
            models.UniqueConstraint(fields=["provider", "external_reference"], name="unique_provider_payment_reference"),
        ]


class Reconciliation(CommercialRecord):
    number = models.CharField(max_length=60, unique=True)
    currency = models.CharField(max_length=3, choices=[("UGX", "UGX"), ("USD", "USD")])
    statement_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=10, choices=[("open", "Open"), ("closed", "Closed")], default="open")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    closed_at = models.DateTimeField(null=True, blank=True)


class StatementLine(CommercialRecord):
    def __str__(self):
        return f"{self.external_reference} / {self.amount} / {self.posted_date}"

    reconciliation = models.ForeignKey(Reconciliation, on_delete=models.PROTECT, related_name="lines")
    external_reference = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    posted_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="statement_line")
    matched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    matched_at = models.DateTimeField(null=True, blank=True)

    class Meta(CommercialRecord.Meta):
        constraints = [models.UniqueConstraint(fields=["reconciliation", "external_reference"], name="unique_statement_line"), models.CheckConstraint(condition=~models.Q(amount=0), name="statement_nonzero_amount")]
