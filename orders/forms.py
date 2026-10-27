from django import forms
from operations.module_ui import ResourceForm, ActionForm
from inventory.models import StockLevel
from .models import Order, ORDER_STATES

class OrderForm(ResourceForm):
    class Meta:
        model = Order
        fields = ["quote", "notes"]

class LineForm(ActionForm):
    stock = forms.ModelChoiceField(queryset=StockLevel.objects.select_related("product", "item__warehouse"))
    quantity_value = forms.DecimalField(label="Quantity", max_digits=15, decimal_places=3, min_value=.001)
    unit_price = forms.DecimalField(max_digits=15, decimal_places=2, min_value=.01)

class TransitionForm(ActionForm):
    target = forms.ChoiceField(choices=ORDER_STATES)
    reason = forms.CharField(required=False, max_length=255)
