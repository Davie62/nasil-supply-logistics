"""Regression suite for fleet readiness, assignments, checkpoints and maintenance."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import EmployeeProfile, User
from core.test_commercial_fixtures import CommercialFixtureMixin
from core.test_helpers import booked_shipment
from fleet.models import RouteCheckpoint
from fleet.services import (
    assign_vehicle,
    complete_maintenance,
    driver_ready,
    record_checkpoint,
    release_assignment,
    save_driver,
    save_vehicle,
    schedule_maintenance,
    vehicle_ready,
)
from shipments.workflows import transition_shipment


class FleetTests(CommercialFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._sequence = 0

    def next_sequence(self):
        self._sequence += 1
        return self._sequence

    def make_vehicle(self, **overrides):
        sequence = self.next_sequence()
        data = {
            "registration": f"UAA{sequence:03d}A", "name": f"QA truck {sequence}",
            "capacity_kg": 1000, "status": "available", "odometer": 100,
            "next_service_date": timezone.localdate() + timedelta(days=30),
            "next_service_odometer": 10000,
        }
        data.update(overrides)
        return save_vehicle(actor=self.maker, data=data)

    def make_driver(self, user=None, **overrides):
        sequence = self.next_sequence()
        if user is None:
            user = User.objects.create_user(
                username=f"qa-driver-{sequence}", email=f"qa-driver-{sequence}@example.com",
                is_staff=True,
            )
        data = {
            "user": user, "license_number": f"DL-{sequence:03d}",
            "license_expires": timezone.localdate() + timedelta(days=365),
            "is_active": True,
        }
        data.update(overrides)
        return save_driver(actor=self.maker, data=data)

    def assign(self, shipment=None, vehicle=None, driver=None, route="Kampala to Jinja"):
        return assign_vehicle(actor=self.maker, data={
            "shipment": shipment or self.shipment,
            "vehicle": vehicle or self.make_vehicle(),
            "driver": driver or self.make_driver(),
            "route": route,
        })

    def dispatch(self, shipment=None):
        shipment = shipment or self.shipment
        return transition_shipment(shipment_id=shipment.pk, actor=self.maker, target="in_transit")

    def test_vehicle_readiness_blocks_unavailable_due_and_scheduled_service(self):
        with self.assertRaisesMessage(ValidationError, "unavailable or maintenance is due"):
            vehicle_ready(self.make_vehicle(status="maintenance"))
        with self.assertRaisesMessage(ValidationError, "unavailable or maintenance is due"):
            vehicle_ready(self.make_vehicle(next_service_date=timezone.localdate()))
        with self.assertRaisesMessage(ValidationError, "unavailable or maintenance is due"):
            vehicle_ready(self.make_vehicle(odometer=500, next_service_odometer=500))

        vehicle = self.make_vehicle()
        schedule_maintenance(actor=self.maker, data={
            "vehicle": vehicle, "description": "Brake inspection",
            "due_date": timezone.localdate(), "due_odometer": 9000,
        })
        with self.assertRaisesMessage(ValidationError, "Scheduled vehicle maintenance is due"):
            vehicle_ready(vehicle)

        with self.assertRaises(ValidationError):
            self.make_vehicle(capacity_kg=0)

    def test_driver_readiness_requires_active_staff_and_a_current_licence(self):
        valid = self.make_driver()
        driver_ready(valid)

        with patch(
            "fleet.services.timezone.localdate",
            return_value=timezone.localdate() + timedelta(days=366),
        ):
            with self.assertRaisesMessage(ValidationError, "current licence"):
                driver_ready(valid)

        plain = User.objects.create_user(username="plain-driver", email="plain-driver@example.com")
        non_staff = self.make_driver(user=plain, is_active=False)
        non_staff.is_active = True
        with self.assertRaisesMessage(ValidationError, "active staff with a current licence"):
            driver_ready(non_staff)

        suspended_user = User.objects.create_user(
            username="suspended-driver", email="suspended-driver@example.com", is_staff=True,
        )
        profile = EmployeeProfile.objects.get(user=suspended_user)
        profile.status = "SUSPENDED"
        profile.save()
        suspended_user._state.fields_cache.pop("profile", None)
        suspended = self.make_driver(user=suspended_user, is_active=False)
        suspended.is_active = True
        with self.assertRaisesMessage(ValidationError, "not on active duty"):
            driver_ready(suspended)

        inactive_user = User.objects.create_user(
            username="inactive-driver", email="inactive-driver@example.com", is_staff=True,
        )
        inactive = self.make_driver(user=inactive_user, is_active=False)
        inactive.is_active = True
        inactive_user.is_active = False
        with self.assertRaisesMessage(ValidationError, "active staff with a current licence"):
            driver_ready(inactive)

    def test_assignment_requires_pending_shipment_and_exclusive_use(self):
        vehicle = self.make_vehicle()
        driver = self.make_driver()
        self.assign(vehicle=vehicle, driver=driver)

        other_shipment = booked_shipment(self.customer)
        with self.assertRaisesMessage(ValidationError, "already has an active assignment"):
            self.assign(shipment=other_shipment, vehicle=vehicle, driver=self.make_driver())
        with self.assertRaisesMessage(ValidationError, "already has an active assignment"):
            self.assign(shipment=other_shipment, vehicle=self.make_vehicle(), driver=driver)
        with self.assertRaisesMessage(ValidationError, "already has an active assignment"):
            self.assign(shipment=self.shipment, vehicle=self.make_vehicle(), driver=self.make_driver())

        in_transit = booked_shipment(self.customer, status="in_transit")
        with self.assertRaisesMessage(ValidationError, "Assign fleet before dispatch"):
            self.assign(shipment=in_transit)

    def test_assignment_rejects_cargo_above_vehicle_capacity(self):
        with self.assertRaisesMessage(ValidationError, "exceeds vehicle capacity"):
            self.assign(vehicle=self.make_vehicle(capacity_kg=5))

    def test_release_requires_a_reason_and_blocks_in_transit_assignments(self):
        assignment = self.assign()
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            release_assignment(actor=self.maker, record_id=assignment.pk, reason="  ")

        self.dispatch()
        with self.assertRaisesMessage(ValidationError, "in transit cannot be released manually"):
            release_assignment(actor=self.maker, record_id=assignment.pk, reason="Change of plans")

        replacement = self.assign(
            shipment=booked_shipment(self.customer), vehicle=self.make_vehicle(),
            driver=self.make_driver(),
        )
        with self.assertRaisesMessage(ValidationError, "changed since you opened"):
            release_assignment(
                actor=self.maker, record_id=replacement.pk,
                expected_version=replacement.version - 1, reason="Stale screen",
            )
        released = release_assignment(
            actor=self.maker, record_id=replacement.pk,
            expected_version=replacement.version, reason="Truck reassigned",
        )
        self.assertIsNotNone(released.released_at)

    def test_released_vehicle_and_driver_become_available_for_reassignment(self):
        vehicle = self.make_vehicle()
        driver = self.make_driver()
        assignment = self.assign(vehicle=vehicle, driver=driver)
        release_assignment(actor=self.maker, record_id=assignment.pk, reason="Load cancelled")

        self.assign(shipment=booked_shipment(self.customer), vehicle=vehicle, driver=driver)
        self.assertEqual(vehicle.assignments.filter(released_at__isnull=True).count(), 1)

    def test_checkpoint_requires_transit_and_valid_coordinates(self):
        assignment = self.assign()
        with self.assertRaisesMessage(ValidationError, "active assignment in transit"):
            record_checkpoint(actor=self.maker, record_id=assignment.pk, location="Mukono")

        self.dispatch()
        with self.assertRaisesMessage(ValidationError, "Provide both valid latitude and longitude"):
            record_checkpoint(actor=self.maker, record_id=assignment.pk, location="Mukono", latitude=0.35)
        with self.assertRaisesMessage(ValidationError, "Provide both valid latitude and longitude"):
            record_checkpoint(
                actor=self.maker, record_id=assignment.pk, location="Mukono",
                latitude=91, longitude=33,
            )

        record_checkpoint(
            actor=self.maker, record_id=assignment.pk, location="Mukono",
            latitude=Decimal("0.353"), longitude=Decimal("33.0"),
        )
        checkpoint = RouteCheckpoint.objects.get(assignment=assignment)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.current_location, "Mukono")
        self.assertEqual(checkpoint.location, "Mukono")
        self.assertEqual(checkpoint.latitude, Decimal("0.353000"))
        self.assertEqual(checkpoint.longitude, Decimal("33.000000"))

    def test_vehicle_edits_guard_odometer_and_active_assignments(self):
        vehicle = self.make_vehicle(registration="  uaa900a  ")
        self.assertEqual(vehicle.registration, "UAA900A")

        with self.assertRaisesMessage(ValidationError, "Odometer cannot move backwards"):
            save_vehicle(
                actor=self.maker, record_id=vehicle.pk,
                data={"odometer": 50, "name": "Rolled back"},
            )

        self.assign(vehicle=vehicle)
        with self.assertRaisesMessage(ValidationError, "Release the active assignment"):
            save_vehicle(
                actor=self.maker, record_id=vehicle.pk,
                data={"odometer": 100, "name": "Busy truck"},
            )

    def test_driver_edits_guard_active_assignments(self):
        driver = self.make_driver()
        self.assign(driver=driver)
        with self.assertRaisesMessage(ValidationError, "Release active driver assignments"):
            save_driver(
                actor=self.maker, record_id=driver.pk,
                data={"license_number": "DL-CHANGED"},
            )

    def test_maintenance_completion_updates_vehicle_and_validates_limits(self):
        vehicle = self.make_vehicle(odometer=100)
        maintenance = schedule_maintenance(actor=self.maker, data={
            "vehicle": vehicle, "description": "Full service",
            "due_date": timezone.localdate() + timedelta(days=5), "due_odometer": 9000,
        })
        future = timezone.localdate() + timedelta(days=60)

        with self.assertRaisesMessage(ValidationError, "increasing odometer"):
            complete_maintenance(
                actor=self.maker, record_id=maintenance.pk, odometer=50,
                next_service_date=future, next_service_odometer=10000,
                cost=0, currency="UGX",
            )
        with self.assertRaisesMessage(ValidationError, "increasing odometer"):
            complete_maintenance(
                actor=self.maker, record_id=maintenance.pk, odometer=150,
                next_service_date=future, next_service_odometer=150,
                cost=0, currency="UGX",
            )
        with self.assertRaisesMessage(ValidationError, "increasing odometer"):
            complete_maintenance(
                actor=self.maker, record_id=maintenance.pk, odometer=150,
                next_service_date=timezone.localdate(), next_service_odometer=10000,
                cost=0, currency="UGX",
            )

        self.assign(shipment=booked_shipment(self.customer), vehicle=vehicle)
        with self.assertRaisesMessage(ValidationError, "Release fleet assignments"):
            complete_maintenance(
                actor=self.maker, record_id=maintenance.pk, odometer=150,
                next_service_date=future, next_service_odometer=10000,
                cost=0, currency="UGX",
            )

        for assignment in vehicle.assignments.filter(released_at__isnull=True):
            release_assignment(actor=self.maker, record_id=assignment.pk, reason="Workshop visit")

        save_vehicle(
            actor=self.maker, record_id=vehicle.pk,
            data={"odometer": 100, "status": "maintenance"},
        )
        completed = complete_maintenance(
            actor=self.maker, record_id=maintenance.pk, odometer=150,
            next_service_date=future, next_service_odometer=10000,
            cost=Decimal("75.50"), currency="UGX",
        )
        vehicle.refresh_from_db()
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.cost, Decimal("75.50"))
        self.assertEqual(vehicle.odometer, 150)
        self.assertEqual(vehicle.next_service_odometer, 10000)
        self.assertEqual(vehicle.next_service_date, future)
        self.assertEqual(vehicle.status, "available")

        with self.assertRaisesMessage(ValidationError, "increasing odometer"):
            complete_maintenance(
                actor=self.maker, record_id=maintenance.pk, odometer=200,
                next_service_date=future, next_service_odometer=10000,
                cost=0, currency="UGX",
            )

    def test_fleet_services_reject_unprivileged_staff(self):
        with self.assertRaises(PermissionDenied):
            save_vehicle(actor=self.outsider, data={
                "registration": "DENIED", "name": "Denied", "capacity_kg": 10,
                "status": "available", "odometer": 0,
                "next_service_date": timezone.localdate() + timedelta(days=1),
                "next_service_odometer": 100,
            })
        with self.assertRaises(PermissionDenied):
            save_driver(actor=self.outsider, data={
                "user": self.approver, "license_number": "DL-DENIED",
                "license_expires": timezone.localdate() + timedelta(days=1), "is_active": True,
            })
        with self.assertRaises(PermissionDenied):
            assign_vehicle(actor=self.outsider, data={
                "shipment": self.shipment, "vehicle": self.make_vehicle(),
                "driver": self.make_driver(), "route": "Denied",
            })
        with self.assertRaises(PermissionDenied):
            schedule_maintenance(actor=self.outsider, data={
                "vehicle": self.make_vehicle(), "description": "Denied",
                "due_date": timezone.localdate() + timedelta(days=1), "due_odometer": 100,
            })
