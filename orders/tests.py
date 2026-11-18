"""Regression suite for the order lifecycle and stock reservation rules."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from core.test_commercial_fixtures import CommercialFixtureMixin
from core.test_helpers import booked_shipment
from fleet.services import assign_vehicle, save_driver, save_vehicle
from inventory.models import Reservation
from orders.models import Order
from orders.services import add_line, save_order, transition_order
from shipments.workflows import transition_shipment


class OrderWorkflowTests(CommercialFixtureMixin, TestCase):
    def make_order(self, quantity=5, unit_price=20, notes="QA"):
        order = save_order(actor=self.maker, data={"quote": self.quote, "notes": notes})
        add_line(
            actor=self.maker, record_id=order.pk, stock=self.stock,
            quantity_value=quantity, unit_price=unit_price,
        )
        return order

    def submitted(self, **kwargs):
        order = self.make_order(**kwargs)
        return transition_order(actor=self.maker, record_id=order.pk, target="submitted")

    def approved(self, **kwargs):
        order = self.submitted(**kwargs)
        return transition_order(actor=self.approver, record_id=order.pk, target="approved")

    def fleet(self):
        vehicle = save_vehicle(actor=self.maker, data={
            "registration": "UAA123A", "name": "QA truck", "capacity_kg": 1000,
            "status": "available", "odometer": 100,
            "next_service_date": timezone.localdate() + timedelta(days=30),
            "next_service_odometer": 10000,
        })
        driver = save_driver(actor=self.maker, data={
            "user": self.approver, "license_number": "DL-QA",
            "license_expires": timezone.localdate() + timedelta(days=365),
            "is_active": True,
        })
        return vehicle, driver

    def test_submission_requires_lines_matching_the_approved_quotation(self):
        order = save_order(actor=self.maker, data={"quote": self.quote, "notes": ""})
        with self.assertRaisesMessage(ValidationError, "must match the approved quotation"):
            transition_order(actor=self.maker, record_id=order.pk, target="submitted")

        add_line(actor=self.maker, record_id=order.pk, stock=self.stock, quantity_value=4, unit_price=20)
        with self.assertRaisesMessage(ValidationError, "must match the approved quotation"):
            transition_order(actor=self.maker, record_id=order.pk, target="submitted")

        add_line(actor=self.maker, record_id=order.pk, stock=self.stock, quantity_value=5, unit_price=20)
        order = transition_order(actor=self.maker, record_id=order.pk, target="submitted")
        self.assertEqual(order.status, "submitted")
        self.assertEqual(order.total, self.quote.total_amount)

    def test_approval_requires_a_separate_administrator_and_reserves_stock(self):
        order = self.submitted()
        with self.assertRaises(PermissionDenied):
            transition_order(actor=self.maker, record_id=order.pk, target="approved")
        self.assertFalse(Reservation.objects.exists())

        order = transition_order(actor=self.approver, record_id=order.pk, target="approved")
        self.assertEqual(order.approved_by, self.approver)
        reservation = Reservation.objects.get(order_line__order=order)
        self.assertEqual(reservation.status, "reserved")
        self.assertEqual(reservation.quantity, Decimal("5.000"))

    def test_insufficient_stock_blocks_approval_without_partial_reservation(self):
        order = self.submitted(quantity=20, unit_price=5)
        with self.assertRaisesMessage(ValidationError, "Insufficient available stock"):
            transition_order(actor=self.approver, record_id=order.pk, target="approved")

        order.refresh_from_db()
        self.assertEqual(order.status, "submitted")
        self.assertIsNone(order.approved_by)
        self.assertFalse(Reservation.objects.exists())

    def test_fulfillment_consumes_reserved_stock_once_and_creates_shipment(self):
        order = self.approved()
        order = transition_order(actor=self.maker, record_id=order.pk, target="fulfilled")
        repeated = transition_order(actor=self.maker, record_id=order.pk, target="fulfilled")

        self.assertEqual(repeated.status, "fulfilled")
        self.assertEqual(self.refreshed_item().quantity, Decimal("5.000"))
        self.assertEqual(Reservation.objects.get(order_line__order=order).status, "consumed")
        self.assertIsNotNone(order.shipment_id)

    def test_cancellation_requires_a_reason_and_releases_reservations(self):
        order = self.approved()
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            transition_order(actor=self.maker, record_id=order.pk, target="cancelled")

        transition_order(
            actor=self.maker, record_id=order.pk, target="cancelled",
            reason="Customer withdrew",
        )
        self.assertFalse(Reservation.objects.filter(status="reserved").exists())
        self.assertEqual(self.refreshed_item().quantity, Decimal("10.000"))
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, "cancelled")

    def test_dispatch_requires_fleet_and_closure_requires_delivery(self):
        order = self.approved()
        order = transition_order(actor=self.maker, record_id=order.pk, target="fulfilled")

        with self.assertRaisesMessage(ValidationError, "fleet vehicle"):
            transition_order(actor=self.maker, record_id=order.pk, target="shipped")

        vehicle, driver = self.fleet()
        assign_vehicle(actor=self.maker, data={
            "shipment": self.shipment, "vehicle": vehicle, "driver": driver,
            "route": "Kampala to Jinja",
        })
        order = transition_order(actor=self.maker, record_id=order.pk, target="shipped")

        with self.assertRaisesMessage(ValidationError, "Delivery must be confirmed"):
            transition_order(actor=self.maker, record_id=order.pk, target="closed")

        transition_shipment(shipment_id=self.shipment.pk, actor=self.maker, target="delivered")
        order = transition_order(actor=self.maker, record_id=order.pk, target="closed")
        self.assertEqual(order.status, "closed")

    def test_stale_version_and_quotation_change_are_rejected(self):
        order = save_order(actor=self.maker, data={"quote": self.quote, "notes": "first"})
        updated = save_order(
            actor=self.maker, data={"quote": self.quote, "notes": "second"},
            record_id=order.pk, expected_version=order.version,
        )
        with self.assertRaisesMessage(ValidationError, "changed since you opened"):
            save_order(
                actor=self.maker, data={"quote": self.quote, "notes": "third"},
                record_id=order.pk, expected_version=order.version,
            )

        other_quote = booked_shipment(self.customer).quote
        with self.assertRaisesMessage(ValidationError, "quotation is fixed"):
            save_order(
                actor=self.maker, data={"quote": other_quote, "notes": "swap"},
                record_id=updated.pk,
            )

    def test_lines_are_locked_after_submission(self):
        order = self.submitted()
        with self.assertRaisesMessage(ValidationError, "draft orders"):
            add_line(
                actor=self.maker, record_id=order.pk, stock=self.stock,
                quantity_value=1, unit_price=100,
            )

    def test_unsupported_fields_and_unprivileged_staff_are_rejected(self):
        with self.assertRaisesMessage(ValidationError, "Unsupported fields"):
            save_order(actor=self.maker, data={"quote": self.quote, "status": "approved"})
        with self.assertRaises(PermissionDenied):
            save_order(actor=self.outsider, data={"quote": self.quote, "notes": ""})

    def test_direct_and_bulk_writes_cannot_bypass_the_workflow(self):
        order = self.make_order()
        order.notes = "Bypass"
        with self.assertRaises(ValidationError):
            order.save()
        with self.assertRaises(ValidationError):
            Order.objects.filter(pk=order.pk).update(notes="Bypass")
        with self.assertRaises(ValidationError):
            Order.objects.bulk_update([order], ["notes"])
