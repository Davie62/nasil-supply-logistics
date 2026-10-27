from django.db import models
from operations.commercial import CommercialRecord
from organization.models import Warehouse as ExistingWarehouse


class Warehouse(ExistingWarehouse):
    class Meta:
        proxy = True


class Product(CommercialRecord):
    sku = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, default="units")
    description = models.TextField(blank=True, max_length=2000)
    is_active = models.BooleanField(default=True)

    class Meta(CommercialRecord.Meta):
        ordering = ["sku"]


class StockLevel(CommercialRecord):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_levels")
    item = models.OneToOneField("operations.InventoryItem", on_delete=models.PROTECT, related_name="catalog_stock")

    @property
    def quantity(self):
        return self.item.quantity

    def __str__(self):
        return f"{self.product.sku} / {self.item.warehouse}"


class Reservation(CommercialRecord):
    stock = models.ForeignKey(StockLevel, on_delete=models.PROTECT, related_name="reservations")
    order_line = models.OneToOneField("orders.OrderLine", on_delete=models.PROTECT, related_name="reservation")
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    status = models.CharField(max_length=10, choices=[("reserved", "Reserved"), ("consumed", "Consumed"), ("released", "Released")], default="reserved")

    class Meta(CommercialRecord.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="reservation_positive_quantity")]
