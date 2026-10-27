from django.conf import settings
from django.db import models
from operations.commercial import CommercialRecord

ORDER_STATES = [(code, code.replace("_", " ").title()) for code in ("draft", "submitted", "approved", "fulfilled", "shipped", "closed", "cancelled")]


class Order(CommercialRecord):
    number = models.CharField(max_length=40, unique=True)
    quote = models.OneToOneField("quotations.Quote", on_delete=models.PROTECT, related_name="sales_order")
    shipment = models.OneToOneField("shipments.Shipment", on_delete=models.PROTECT, null=True, blank=True, related_name="sales_order")
    status = models.CharField(max_length=20, choices=ORDER_STATES, default="draft")
    currency = models.CharField(max_length=3)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True, max_length=2000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prepared_orders")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="approved_orders")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta(CommercialRecord.Meta):
        permissions = [("approve_order", "Can approve customer orders"), ("fulfill_order", "Can fulfill customer orders")]
        constraints = [models.CheckConstraint(condition=models.Q(total__gte=0, currency__in=["UGX", "USD"], status__in=[value[0] for value in ORDER_STATES]), name="order_valid_commercial_values")]


class OrderLine(CommercialRecord):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="lines")
    stock = models.ForeignKey("inventory.StockLevel", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta(CommercialRecord.Meta):
        constraints = [models.UniqueConstraint(fields=["order", "stock"], name="unique_order_stock"), models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gt=0, line_total__gt=0), name="order_line_positive")]
