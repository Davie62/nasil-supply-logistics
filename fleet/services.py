from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.utils import timezone
from core.business_rules import require_permission, validate_version
from operations.commercial import persist, editable_data, money
from shipments.models import Shipment
from quotations.models import Quote
from .models import Vehicle, Driver, Assignment, RouteCheckpoint, Maintenance


def vehicle_ready(vehicle):
    if vehicle.status != "available" or vehicle.next_service_date <= timezone.localdate() or vehicle.odometer >= vehicle.next_service_odometer:
        raise ValidationError("Vehicle is unavailable or maintenance is due.")
    if vehicle.maintenance_records.filter(status="scheduled", due_date__lte=timezone.localdate()).exists() or vehicle.maintenance_records.filter(status="scheduled", due_odometer__lte=vehicle.odometer).exists():
        raise ValidationError("Scheduled vehicle maintenance is due.")


def driver_ready(driver):
    if not driver.is_active or not driver.user.is_active or not driver.user.is_staff or driver.license_expires < timezone.localdate():
        raise ValidationError("Driver must be active staff with a current licence.")
    profile = getattr(driver.user, "profile", None)
    if profile and profile.status != "ACTIVE":
        raise ValidationError("The driver is not on active duty.")


@transaction.atomic
def save_vehicle(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "fleet.change_vehicle" if record_id else "fleet.add_vehicle")
    editable_data(data, ("registration", "name", "capacity_kg", "status", "odometer", "next_service_date", "next_service_odometer"))
    vehicle = Vehicle.objects.select_for_update().get(pk=record_id) if record_id else Vehicle()
    validate_version(vehicle, expected_version)
    if record_id and data["odometer"] < vehicle.odometer:
        raise ValidationError("Odometer cannot move backwards.")
    if record_id and vehicle.assignments.filter(released_at__isnull=True).exists():
        raise ValidationError("Release the active assignment before editing the vehicle.")
    for key, value in data.items():
        setattr(vehicle, key, value)
    vehicle.registration = vehicle.registration.strip().upper()
    return persist(vehicle, actor, "vehicle_saved")


@transaction.atomic
def save_driver(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "fleet.change_driver" if record_id else "fleet.add_driver")
    editable_data(data, ("user", "license_number", "license_expires", "is_active"))
    driver = Driver.objects.select_for_update().get(pk=record_id) if record_id else Driver()
    validate_version(driver, expected_version)
    if record_id and driver.assignments.filter(released_at__isnull=True).exists():
        raise ValidationError("Release active driver assignments before editing.")
    for key, value in data.items():
        setattr(driver, key, value)
    if driver.is_active:
        driver_ready(driver)
    return persist(driver, actor, "driver_saved")


@transaction.atomic
def assign_vehicle(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "fleet.add_assignment", "shipments.view_shipment")
    editable_data(data, ("shipment", "vehicle", "driver", "route"))
    if record_id:
        raise ValidationError("Release assignments and create a new assignment; history is retained.")
    quote_id = Shipment.objects.values_list("quote_id", flat=True).get(pk=data["shipment"].pk)
    quote = Quote.objects.select_for_update().get(pk=quote_id)
    shipment = Shipment.objects.select_for_update().get(pk=data["shipment"].pk)
    vehicle = Vehicle.objects.select_for_update().get(pk=data["vehicle"].pk)
    driver = Driver.objects.select_for_update().select_related("user").get(pk=data["driver"].pk)
    if shipment.status != "pending":
        raise ValidationError("Assign fleet before dispatch.")
    vehicle_ready(vehicle)
    driver_ready(driver)
    if quote.weight > vehicle.capacity_kg:
        raise ValidationError("Shipment weight exceeds vehicle capacity.")
    if Assignment.objects.filter(released_at__isnull=True).filter(models.Q(vehicle=vehicle) | models.Q(driver=driver) | models.Q(shipment=shipment)).exists():
        raise ValidationError("This shipment, vehicle or driver already has an active assignment.")
    return persist(Assignment(shipment=shipment, vehicle=vehicle, driver=driver, route=data["route"], assigned_by=actor), actor, "fleet_assigned")


@transaction.atomic
def release_assignment(*, actor, record_id, expected_version=None, reason=""):
    require_permission(actor, "fleet.change_assignment")
    assignment = Assignment.objects.select_related("shipment").get(pk=record_id)
    Quote.objects.select_for_update().get(pk=assignment.shipment.quote_id)
    shipment = Shipment.objects.select_for_update().get(pk=assignment.shipment_id)
    assignment = Assignment.objects.select_for_update().get(pk=record_id)
    validate_version(assignment, expected_version)
    if shipment.status == "in_transit" or not reason.strip():
        raise ValidationError("A reason is required; assignments in transit cannot be released manually.")
    if not assignment.released_at:
        assignment.released_at = timezone.now()
        persist(assignment, actor, "assignment_released", reason=reason)
    return assignment


def validate_dispatch(shipment):
    assignment = Assignment.objects.select_related("vehicle", "driver__user").filter(shipment=shipment, released_at__isnull=True).first()
    # External carriers remain available for legacy/non-order shipments.
    if not assignment:
        from orders.models import Order
        if Order.objects.filter(quote_id=shipment.quote_id).exists():
            raise ValidationError("Assign an available fleet vehicle and driver before dispatching an order.")
        return
    vehicle_ready(assignment.vehicle)
    driver_ready(assignment.driver)


def release_completed(shipment, actor):
    for assignment in Assignment.objects.select_for_update().filter(shipment=shipment, released_at__isnull=True):
        assignment.released_at = timezone.now()
        persist(assignment, actor, "assignment_completed", shipment_status=shipment.status)


@transaction.atomic
def record_checkpoint(*, actor, record_id, location, latitude=None, longitude=None, expected_version=None):
    require_permission(actor, "fleet.add_routecheckpoint", "shipments.change_shipment")
    assignment = Assignment.objects.select_related("shipment").get(pk=record_id)
    Quote.objects.select_for_update().get(pk=assignment.shipment.quote_id)
    shipment = Shipment.objects.select_for_update().get(pk=assignment.shipment_id)
    assignment = Assignment.objects.select_for_update().get(pk=record_id)
    validate_version(assignment, expected_version)
    if assignment.released_at or shipment.status != "in_transit":
        raise ValidationError("Route updates require an active assignment in transit.")
    if (latitude is None) != (longitude is None) or (latitude is not None and not (-90 <= latitude <= 90 and -180 <= longitude <= 180)):
        raise ValidationError("Provide both valid latitude and longitude, or neither.")
    persist(RouteCheckpoint(assignment=assignment, location=location, latitude=latitude, longitude=longitude, recorded_by=actor), actor, "route_checkpoint")
    from shipments.workflows import update_shipment
    update_shipment(shipment_id=shipment.pk, actor=actor, current_location=location)
    return persist(assignment, actor, "route_updated", location=location)


@transaction.atomic
def schedule_maintenance(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "fleet.add_maintenance")
    editable_data(data, ("vehicle", "description", "due_date", "due_odometer"))
    if record_id:
        raise ValidationError("Maintenance records are retained; complete the scheduled record.")
    Vehicle.objects.select_for_update().get(pk=data["vehicle"].pk)
    return persist(Maintenance(**data), actor, "maintenance_scheduled")


@transaction.atomic
def complete_maintenance(*, actor, record_id, odometer, next_service_date, next_service_odometer, cost, currency, expected_version=None):
    require_permission(actor, "fleet.change_maintenance", "fleet.change_vehicle")
    vehicle_id = Maintenance.objects.values_list("vehicle_id", flat=True).get(pk=record_id)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    maintenance = Maintenance.objects.select_for_update().get(pk=record_id)
    validate_version(maintenance, expected_version)
    if maintenance.status != "scheduled" or vehicle.assignments.filter(released_at__isnull=True).exists() or odometer < vehicle.odometer or next_service_odometer <= odometer or next_service_date <= timezone.localdate():
        raise ValidationError("Release fleet assignments and provide increasing odometer/future service limits.")
    maintenance.status, maintenance.completed_at, maintenance.completed_by = "completed", timezone.now(), actor
    maintenance.cost, maintenance.currency = money(cost, positive=False), currency
    vehicle.odometer, vehicle.next_service_date, vehicle.next_service_odometer, vehicle.status = odometer, next_service_date, next_service_odometer, "available"
    persist(vehicle, actor, "vehicle_serviced")
    return persist(maintenance, actor, "maintenance_completed")
