from django import forms
from operations.module_ui import ResourceForm, ActionForm
from .models import Product, StockLevel, Warehouse

class ProductForm(ResourceForm):
    class Meta:
        model = Product
        fields = ["sku", "name", "unit", "description", "is_active"]

class StockForm(ResourceForm):
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.filter(is_active=True))
    reorder_level = forms.DecimalField(min_value=0, max_digits=15, decimal_places=3)
    is_active = forms.BooleanField(required=False, initial=True)
    class Meta:
        model = StockLevel
        fields = ["product"]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial.update(warehouse=self.instance.item.warehouse_id, reorder_level=self.instance.item.reorder_level, is_active=self.instance.item.is_active)

class WarehouseForm(ResourceForm):
    class Meta:
        model = Warehouse
        fields = ["branch", "name", "code", "location", "capacity", "manager", "is_active"]

class AdjustmentForm(ActionForm):
    quantity_change = forms.DecimalField(max_digits=15, decimal_places=3)
    reason = forms.CharField(max_length=255)
