from django import forms
from operations.module_ui import ResourceForm, ActionForm
from .models import Vehicle, Driver, Assignment, Maintenance

class VehicleForm(ResourceForm):
    class Meta:
        model = Vehicle
        fields = ["registration", "name", "capacity_kg", "status", "odometer", "next_service_date", "next_service_odometer"]
        widgets = {"next_service_date": forms.DateInput(attrs={"type": "date"})}

class DriverForm(ResourceForm):
    class Meta:
        model = Driver
        fields = ["user", "license_number", "license_expires", "is_active"]
        widgets = {"license_expires": forms.DateInput(attrs={"type": "date"})}

class AssignmentForm(ResourceForm):
    class Meta:
        model = Assignment
        fields = ["shipment", "vehicle", "driver", "route"]

class MaintenanceForm(ResourceForm):
    class Meta:
        model = Maintenance
        fields = ["vehicle", "description", "due_date", "due_odometer"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

class CheckpointForm(ActionForm):
    location = forms.CharField(max_length=255)
    latitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, min_value=-180, max_value=180)

class CompleteMaintenanceForm(ActionForm):
    odometer = forms.IntegerField(min_value=0)
    next_service_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    next_service_odometer = forms.IntegerField(min_value=1)
    cost = forms.DecimalField(min_value=0, max_digits=15, decimal_places=2)
    currency = forms.ChoiceField(choices=[("UGX", "UGX"), ("USD", "USD")])
