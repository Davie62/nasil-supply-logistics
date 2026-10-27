from django.conf import settings
from django.db import models
from operations.commercial import CommercialRecord


class Vehicle(CommercialRecord):
    registration = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    capacity_kg = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=15, choices=[("available", "Available"), ("maintenance", "In maintenance"), ("retired", "Retired")], default="available")
    odometer = models.PositiveIntegerField(default=0)
    next_service_date = models.DateField()
    next_service_odometer = models.PositiveIntegerField()

    class Meta(CommercialRecord.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(capacity_kg__gt=0), name="vehicle_positive_capacity")]


class Driver(CommercialRecord):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    license_number = models.CharField(max_length=60, unique=True)
    license_expires = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} / {self.license_number}"


class Assignment(CommercialRecord):
    shipment = models.ForeignKey("shipments.Shipment", on_delete=models.PROTECT, related_name="fleet_assignments")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="assignments")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="assignments")
    route = models.CharField(max_length=255)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta(CommercialRecord.Meta):
        constraints = [models.UniqueConstraint(fields=[field], condition=models.Q(released_at__isnull=True), name=f"one_active_assignment_{field}") for field in ("vehicle", "driver", "shipment")]


class RouteCheckpoint(CommercialRecord):
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name="checkpoints")
    location = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class Maintenance(CommercialRecord):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="maintenance_records")
    description = models.CharField(max_length=255)
    due_date = models.DateField()
    due_odometer = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=[("scheduled", "Scheduled"), ("completed", "Completed")], default="scheduled")
    completed_at = models.DateTimeField(null=True, blank=True)
    cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, choices=[("UGX", "UGX"), ("USD", "USD")], default="UGX")
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
