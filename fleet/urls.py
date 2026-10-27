from django.urls import path
from django.utils import timezone
from django.db.models import Q, F
from operations.module_ui import resource_urls, home_view, Action, ReasonForm
from .models import Vehicle, Driver, Assignment, Maintenance
from .forms import VehicleForm, DriverForm, AssignmentForm, MaintenanceForm, CheckpointForm, CompleteMaintenanceForm
from .services import save_vehicle, save_driver, assign_vehicle, release_assignment, record_checkpoint, schedule_maintenance, complete_maintenance

app_name = "fleet"
urlpatterns = [path("", home_view("Fleet operations", [("Vehicles", "fleet:vehicles_list", "fleet.view_vehicle"), ("Drivers", "fleet:drivers_list", "fleet.view_driver"),
    ("Assignments & routes", "fleet:assignments_list", "fleet.view_assignment"), ("Maintenance", "fleet:maintenance_list", "fleet.view_maintenance")],
    lambda request: [("Vehicles", Vehicle.objects.count()), ("Vehicles due for service", Vehicle.objects.exclude(status="retired").filter(Q(next_service_date__lte=timezone.localdate()) | Q(odometer__gte=F("next_service_odometer"))).count()), ("Active assignments", Assignment.objects.filter(released_at__isnull=True).count()),
        ("Maintenance overdue", Maintenance.objects.filter(status="scheduled", due_date__lte=timezone.localdate()).count())]), name="home")]
urlpatterns += resource_urls(model=Vehicle, slug="vehicles", form_class=VehicleForm, save=save_vehicle,
    columns=["Registration", "Vehicle", "Capacity kg", "Status", "Odometer", "Service date", "Service odometer"], fields=["registration", "name", "capacity_kg", "get_status_display", "odometer", "next_service_date", "next_service_odometer"], search_fields=["registration", "name"])
urlpatterns += resource_urls(model=Driver, slug="drivers", form_class=DriverForm, save=save_driver,
    columns=["Staff", "Licence", "Expires", "Active"], fields=["user", "license_number", "license_expires", "is_active"], search_fields=["user__username", "license_number"], select=["user"])
urlpatterns += resource_urls(model=Assignment, slug="assignments", form_class=AssignmentForm, save=assign_vehicle,
    columns=["Shipment", "Vehicle", "Driver", "Route", "Assigned", "Released"], fields=["shipment", "vehicle", "driver", "route", "created_at", "released_at"], search_fields=["shipment__tracking_number", "vehicle__registration", "driver__user__username"], select=["shipment", "vehicle", "driver__user"],
    actions={"release": Action("Release assignment", "fleet.change_assignment", lambda obj: ReasonForm, release_assignment), "checkpoint": Action("Record route checkpoint", "fleet.add_routecheckpoint", lambda obj: CheckpointForm, record_checkpoint)},
    related=lambda obj: [{"title": "Route tracking history", "columns": ["Location", "Latitude", "Longitude", "Timestamp", "Recorded by"], "rows": obj.checkpoints.values_list("location", "latitude", "longitude", "created_at", "recorded_by__username")[:100]}])
urlpatterns += resource_urls(model=Maintenance, slug="maintenance", form_class=MaintenanceForm, save=schedule_maintenance,
    columns=["Vehicle", "Work", "Due date", "Due odometer", "Status", "Completed", "Cost", "Currency"], fields=["vehicle", "description", "due_date", "due_odometer", "get_status_display", "completed_at", "cost", "currency"], search_fields=["vehicle__registration", "description"], select=["vehicle"],
    actions={"complete": Action("Complete maintenance", "fleet.change_maintenance", lambda obj: CompleteMaintenanceForm, complete_maintenance)})
