"""Regression suite for supplier audits, procurement budgets and goods receipts."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from core.test_commercial_fixtures import CommercialFixtureMixin
from finance.services import record_payment
from procurement.models import GoodsReceipt, PurchaseOrder
from procurement.services import (
    add_purchase_line,
    audit_supplier,
    receive_goods,
    save_purchase_order,
    save_request,
    save_supplier,
    transition_purchase,
    transition_request,
)


class ProcurementTests(CommercialFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._supplier_seq = 0

    def make_supplier(self, outcome="pass", valid_days=30):
        self._supplier_seq += 1
        supplier = save_supplier(actor=self.maker, data={
            "name": f"QA supplier {self._supplier_seq}",
            "registration_number": f"SUP-{self._supplier_seq:03d}",
            "email": f"supplier{self._supplier_seq}@example.com", "phone": "0",
            "address": "Kampala", "is_active": True,
        })
        audit_supplier(
            actor=self.maker, record_id=supplier.pk, outcome=outcome,
            valid_until=timezone.localdate() + timedelta(days=valid_days),
            notes="Supplier verified",
        )
        return supplier

    def make_request(self, budget=400):
        request = save_request(actor=self.maker, data={
            "purpose": "Stock replenishment", "currency": "UGX",
            "budget": budget, "order": None,
        })
        transition_request(actor=self.maker, record_id=request.pk, target="submitted")
        return transition_request(actor=self.approver, record_id=request.pk, target="approved")

    def make_purchase(self, budget=400, quantity=10, unit_price=20, supplier=None):
        request = self.make_request(budget)
        purchase = save_purchase_order(actor=self.maker, data={
            "request": request, "supplier": supplier or self.make_supplier(),
        })
        add_purchase_line(
            actor=self.maker, record_id=purchase.pk, stock=self.stock,
            quantity_value=quantity, unit_price=unit_price,
        )
        transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")
        purchase = transition_purchase(actor=self.approver, record_id=purchase.pk, target="approved")
        return transition_purchase(actor=self.maker, record_id=purchase.pk, target="sent")

    def test_purchase_order_requires_a_current_passing_supplier_audit(self):
        request = self.make_request()
        unaudited = save_supplier(actor=self.maker, data={
            "name": "Unaudited", "registration_number": "SUP-UNAUDITED",
            "email": "unaudited@example.com", "phone": "0",
            "address": "Kampala", "is_active": True,
        })
        with self.assertRaisesMessage(ValidationError, "current passing audit"):
            save_purchase_order(actor=self.maker, data={"request": request, "supplier": unaudited})

        failed = self.make_supplier(outcome="fail")
        with self.assertRaisesMessage(ValidationError, "current passing audit"):
            save_purchase_order(actor=self.maker, data={"request": request, "supplier": failed})

        current = self.make_supplier()
        with patch(
            "procurement.services.timezone.localdate",
            return_value=timezone.localdate() + timedelta(days=31),
        ):
            with self.assertRaisesMessage(ValidationError, "current passing audit"):
                save_purchase_order(actor=self.maker, data={"request": request, "supplier": current})

        purchase = save_purchase_order(actor=self.maker, data={"request": request, "supplier": current})
        self.assertEqual(purchase.supplier, current)

    def test_request_requires_separate_administrator_approval(self):
        request = save_request(actor=self.maker, data={
            "purpose": "Stock replenishment", "currency": "UGX",
            "budget": 400, "order": None,
        })
        transition_request(actor=self.maker, record_id=request.pk, target="submitted")

        with self.assertRaises(PermissionDenied):
            transition_request(actor=self.maker, record_id=request.pk, target="approved")

        self.maker.user_permissions.add(
            Permission.objects.get(codename="approve_procurementrequest")
        )
        self.maker = User.objects.get(pk=self.maker.pk)
        with self.assertRaisesMessage(ValidationError, "preparer cannot approve"):
            transition_request(actor=self.maker, record_id=request.pk, target="approved")

        approved = transition_request(actor=self.approver, record_id=request.pk, target="approved")
        self.assertEqual(approved.approved_by, self.approver)

    def test_request_is_immutable_after_submission_and_requires_a_budget(self):
        with self.assertRaises(ValidationError):
            save_request(actor=self.maker, data={
                "purpose": "Zero budget", "currency": "UGX",
                "budget": 0, "order": None,
            })

        request = save_request(actor=self.maker, data={
            "purpose": "Stock replenishment", "currency": "UGX",
            "budget": 400, "order": None,
        })
        transition_request(actor=self.maker, record_id=request.pk, target="submitted")
        with self.assertRaisesMessage(ValidationError, "Only draft procurement requests"):
            save_request(actor=self.maker, data={"purpose": "Changed"}, record_id=request.pk)

    def test_purchase_requires_approved_request_and_lines_within_budget(self):
        draft = save_request(actor=self.maker, data={
            "purpose": "Stock replenishment", "currency": "UGX",
            "budget": 400, "order": None,
        })
        with self.assertRaisesMessage(ValidationError, "Approve the procurement request first"):
            save_purchase_order(actor=self.maker, data={"request": draft, "supplier": self.make_supplier()})

        request = self.make_request(budget=150)
        purchase = save_purchase_order(actor=self.maker, data={
            "request": request, "supplier": self.make_supplier(),
        })
        with self.assertRaisesMessage(ValidationError, "positive purchase lines"):
            transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")

        add_purchase_line(
            actor=self.maker, record_id=purchase.pk, stock=self.stock,
            quantity_value=10, unit_price=20,
        )
        with self.assertRaisesMessage(ValidationError, "within its budget"):
            transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")

    def test_purchase_transition_requires_a_current_supplier_audit(self):
        supplier = self.make_supplier()
        request = self.make_request()
        purchase = save_purchase_order(actor=self.maker, data={"request": request, "supplier": supplier})
        add_purchase_line(
            actor=self.maker, record_id=purchase.pk, stock=self.stock,
            quantity_value=10, unit_price=20,
        )

        audit_supplier(
            actor=self.maker, record_id=supplier.pk, outcome="fail",
            valid_until=timezone.localdate() + timedelta(days=30), notes="Compliance failed",
        )
        with self.assertRaisesMessage(ValidationError, "current passing audit"):
            transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")

        audit_supplier(
            actor=self.maker, record_id=supplier.pk, outcome="pass",
            valid_until=timezone.localdate() + timedelta(days=30), notes="Compliance restored",
        )
        submitted = transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")
        self.assertEqual(submitted.status, "submitted")

    def test_receipt_is_idempotent_and_cannot_exceed_ordered_quantity(self):
        purchase = self.make_purchase()
        line = purchase.lines.get()

        receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=4, delivery_reference="REC-1")
        receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=4, delivery_reference="REC-1")
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(self.refreshed_item().quantity, Decimal("14.000"))

        with self.assertRaisesMessage(ValidationError, "exceeds the outstanding"):
            receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=7, delivery_reference="REC-2")
        with self.assertRaisesMessage(ValidationError, "already used for different goods"):
            receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=5, delivery_reference="REC-1")

        receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=6, delivery_reference="REC-2")
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "received")
        self.assertEqual(GoodsReceipt.objects.count(), 2)
        self.assertEqual(self.refreshed_item().quantity, Decimal("20.000"))

    def test_receipt_requires_a_sent_purchase_order(self):
        request = self.make_request()
        purchase = save_purchase_order(actor=self.maker, data={"request": request, "supplier": self.make_supplier()})
        add_purchase_line(
            actor=self.maker, record_id=purchase.pk, stock=self.stock,
            quantity_value=10, unit_price=20,
        )
        transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")
        transition_purchase(actor=self.approver, record_id=purchase.pk, target="approved")

        with self.assertRaisesMessage(ValidationError, "Only sent purchase orders"):
            receive_goods(
                actor=self.maker, record_id=purchase.pk, line=purchase.lines.get(),
                quantity_value=1, delivery_reference="EARLY",
            )

    def test_purchase_cancellation_guards_received_and_paid_orders(self):
        purchase = self.make_purchase()
        with self.assertRaisesMessage(ValidationError, "reason"):
            transition_purchase(actor=self.maker, record_id=purchase.pk, target="cancelled")

        record_payment(
            actor=self.maker, purchase_order=purchase, amount=200, currency="UGX",
            method="bank", external_reference="PO-PAY", idempotency_key="po-pay",
        )
        with self.assertRaisesMessage(ValidationError, "received or paid"):
            transition_purchase(
                actor=self.maker, record_id=purchase.pk, target="cancelled",
                reason="No longer needed",
            )

        received = self.make_purchase()
        receive_goods(
            actor=self.maker, record_id=received.pk, line=received.lines.get(),
            quantity_value=10, delivery_reference="FULL-RECEIPT",
        )
        with self.assertRaisesMessage(ValidationError, "Cannot change status from received"):
            transition_purchase(
                actor=self.maker, record_id=received.pk, target="cancelled",
                reason="Supplier dispute",
            )

    def test_request_cancellation_requires_a_reason_and_no_live_purchase_order(self):
        purchase = self.make_purchase()
        request = purchase.request

        with self.assertRaisesMessage(ValidationError, "cancel any linked purchase order"):
            transition_request(
                actor=self.maker, record_id=request.pk, target="cancelled",
                reason="Stop the purchase",
            )

        transition_purchase(
            actor=self.maker, record_id=purchase.pk, target="cancelled",
            reason="Request withdrawn",
        )
        cancelled = transition_request(
            actor=self.maker, record_id=request.pk, target="cancelled",
            reason="Request withdrawn",
        )
        self.assertEqual(cancelled.status, "cancelled")

    def test_procurement_services_reject_unprivileged_staff(self):
        with self.assertRaises(PermissionDenied):
            save_supplier(actor=self.outsider, data={
                "name": "Denied", "registration_number": "SUP-DENIED",
                "email": "denied@example.com", "phone": "0",
                "address": "Kampala", "is_active": True,
            })
        with self.assertRaises(PermissionDenied):
            save_request(actor=self.outsider, data={
                "purpose": "Denied", "currency": "UGX", "budget": 10, "order": None,
            })
        purchase = self.make_purchase()
        with self.assertRaises(PermissionDenied):
            receive_goods(
                actor=self.outsider, record_id=purchase.pk, line=purchase.lines.get(),
                quantity_value=1, delivery_reference="DENIED",
            )

    def test_purchase_totals_are_derived_from_lines(self):
        purchase = self.make_purchase(quantity=3, unit_price=20)
        purchase.refresh_from_db()
        self.assertEqual(purchase.total, Decimal("60.00"))
        self.assertEqual(PurchaseOrder.objects.get(pk=purchase.pk).total, purchase.total)
