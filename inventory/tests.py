"""Regression suite for catalogue stock, reservations and stock-movement rules."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.test_commercial_fixtures import CommercialFixtureMixin
from core.test_helpers import booked_shipment
from inventory.models import Reservation
from inventory.services import adjust_stock, save_product, save_stock, save_warehouse
from operations.models import InventoryItem
from operations.services import save_inventory
from orders.services import add_line, save_order, transition_order


class InventoryTests(CommercialFixtureMixin, TestCase):
    def order_for(self, shipment, quantity=5, unit_price=20):
        order = save_order(actor=self.maker, data={"quote": shipment.quote, "notes": ""})
        add_line(
            actor=self.maker, record_id=order.pk, stock=self.stock,
            quantity_value=quantity, unit_price=unit_price,
        )
        transition_order(actor=self.maker, record_id=order.pk, target="submitted")
        return order

    def test_product_sku_is_normalized_and_must_be_unique(self):
        product = save_product(actor=self.maker, data={
            "sku": " pallet-01 ", "name": "Pallets", "unit": "units",
            "description": "", "is_active": True,
        })
        self.assertEqual(product.sku, "PALLET-01")
        with self.assertRaises(ValidationError):
            save_product(actor=self.maker, data={
                "sku": "PALLET-01", "name": "Duplicate", "unit": "units",
                "description": "", "is_active": True,
            })

    def test_sku_and_unit_are_locked_once_stock_exists(self):
        with self.assertRaisesMessage(ValidationError, "SKU and unit are locked"):
            save_product(actor=self.maker, data={"sku": "NEW-SKU"}, record_id=self.product.pk)
        renamed = save_product(actor=self.maker, data={"name": "Renamed crates"}, record_id=self.product.pk)
        self.assertEqual(renamed.name, "Renamed crates")
        self.assertEqual(renamed.sku, "QA-001")

    def test_product_and_warehouse_cannot_be_archived_with_open_reservations(self):
        order = self.order_for(self.shipment)
        transition_order(actor=self.approver, record_id=order.pk, target="approved")

        with self.assertRaisesMessage(ValidationError, "open reservations"):
            save_product(actor=self.maker, data={"is_active": False}, record_id=self.product.pk)

        with self.assertRaisesMessage(ValidationError, "Release reservations"):
            save_warehouse(actor=self.maker, record_id=self.warehouse.pk, data={
                "branch": self.branch, "name": self.warehouse.name,
                "code": self.warehouse.code, "location": self.warehouse.location,
                "capacity": None, "manager": "", "is_active": False,
            })

    def test_stock_link_rejects_a_legacy_unit_mismatch(self):
        save_inventory(actor=self.maker, data={
            "sku": "MISMATCH", "name": "Legacy stock", "warehouse": self.warehouse,
            "unit": "boxes", "reorder_level": 0, "is_active": True,
        })
        product = save_product(actor=self.maker, data={
            "sku": "MISMATCH", "name": "Catalogue stock", "unit": "units",
            "description": "", "is_active": True,
        })
        with self.assertRaisesMessage(ValidationError, "different unit"):
            save_stock(actor=self.maker, data={
                "product": product, "warehouse": self.warehouse,
                "reorder_level": 0, "is_active": True,
            })

    def test_adjust_stock_validates_quantity_reason_and_active_records(self):
        with self.assertRaises(ValidationError):
            adjust_stock(actor=self.maker, record_id=self.stock.pk, quantity_change=0, reason="No change")
        with self.assertRaises(ValidationError):
            adjust_stock(actor=self.maker, record_id=self.stock.pk, quantity_change=1, reason="   ")

        adjust_stock(actor=self.maker, record_id=self.stock.pk, quantity_change=2.5, reason="Cycle count")
        self.assertEqual(self.refreshed_item().quantity, Decimal("12.500"))

    def test_reservations_account_for_existing_holds(self):
        first = self.order_for(self.shipment, quantity=8, unit_price=Decimal("12.5"))
        transition_order(actor=self.approver, record_id=first.pk, target="approved")

        second = self.order_for(booked_shipment(self.customer), quantity=5, unit_price=20)
        with self.assertRaisesMessage(ValidationError, "Insufficient available stock"):
            transition_order(actor=self.approver, record_id=second.pk, target="approved")

        adjust_stock(actor=self.maker, record_id=self.stock.pk, quantity_change=10, reason="Replenishment")
        transition_order(actor=self.approver, record_id=second.pk, target="approved")
        self.assertEqual(Reservation.objects.filter(status="reserved").count(), 2)

    def test_release_returns_reserved_stock_without_consuming_it(self):
        order = self.order_for(self.shipment)
        transition_order(actor=self.approver, record_id=order.pk, target="approved")
        transition_order(
            actor=self.maker, record_id=order.pk, target="cancelled",
            reason="Order cancelled",
        )

        self.assertEqual(Reservation.objects.get(order_line__order=order).status, "released")
        self.assertEqual(self.refreshed_item().quantity, Decimal("10.000"))

    def test_services_reject_unprivileged_staff(self):
        with self.assertRaises(PermissionDenied):
            save_product(actor=self.outsider, data={
                "sku": "DENIED", "name": "Denied", "unit": "units",
                "description": "", "is_active": True,
            })
        with self.assertRaises(PermissionDenied):
            adjust_stock(actor=self.outsider, record_id=self.stock.pk, quantity_change=1, reason="Denied")
        with self.assertRaises(PermissionDenied):
            save_stock(actor=self.outsider, data={
                "product": self.product, "warehouse": self.warehouse,
                "reorder_level": 0, "is_active": True,
            })

    def test_catalogue_stock_balance_cannot_be_written_directly(self):
        item = InventoryItem.objects.get(pk=self.item.pk)
        item.quantity = Decimal("999.000")
        with self.assertRaises(ValidationError):
            item.save()
