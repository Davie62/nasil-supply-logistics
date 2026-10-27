from django.db import models
from operations.commercial import CommercialRecord


class Connection(CommercialRecord):
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=40, unique=True)
    kind = models.CharField(max_length=20, choices=[("erp", "ERP"), ("accounting", "Accounting"), ("payment_gateway", "Payment gateway")])
    base_url = models.URLField()
    credential_env = models.CharField(max_length=100, help_text="Name of the environment variable containing the API token; never enter the token itself.")
    webhook_secret_env = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=False)


class IntegrationJob(CommercialRecord):
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT, related_name="jobs")
    operation = models.CharField(max_length=30, choices=[("invoice", "Invoice"), ("invoice_void", "Invoice cancellation"), ("purchase_order", "Purchase order"), ("purchase_void", "Purchase cancellation"), ("gateway_init", "Payment initiation"), ("gateway_verify", "Payment verification")])
    event_key = models.CharField(max_length=150, unique=True)
    payload = models.JSONField()
    status = models.CharField(max_length=15, choices=[(value, value.title()) for value in ("queued", "processing", "retry", "succeeded", "failed")], default="queued", db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    remote_reference = models.CharField(max_length=150, blank=True)


class WebhookEvent(CommercialRecord):
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT)
    event_id = models.CharField(max_length=120)
    payload_digest = models.CharField(max_length=64)
    payment = models.OneToOneField("finance.Payment", on_delete=models.PROTECT)

    class Meta(CommercialRecord.Meta):
        constraints = [models.UniqueConstraint(fields=["connection", "event_id"], name="unique_gateway_event")]


class GatewayIntent(CommercialRecord):
    connection = models.ForeignKey(Connection, on_delete=models.PROTECT)
    invoice = models.ForeignKey("payments.Invoice", on_delete=models.PROTECT, related_name="gateway_intents")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=15, choices=[(value, value.title()) for value in ("created", "pending", "succeeded", "failed", "review")], default="created")
    checkout_url = models.URLField(max_length=1000, blank=True)
    phone = models.CharField(max_length=16, blank=True)
    mobile_provider = models.CharField(max_length=50, blank=True)
    provider_transaction = models.CharField(max_length=150, blank=True)
    payment = models.OneToOneField("finance.Payment", on_delete=models.PROTECT, null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    error_code = models.CharField(max_length=80, blank=True)

    class Meta(CommercialRecord.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0, currency__in=["UGX", "USD"]), name="gateway_positive_intent")]
