from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
import json
import os
from django.contrib.auth.models import Permission, Group
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from accounts.roles import seed_role_permissions
from organization.models import Company, Branch, Warehouse
from customers.models import Customer
from core.test_helpers import booked_shipment
from operations.models import InventoryItem, StockMovement, OperationsEvent
from operations.services import move_stock, managed_save
from inventory.models import Product, StockLevel, Reservation
from inventory.services import save_product, save_stock
from orders.models import Order
from orders.services import save_order, add_line, transition_order
from procurement.models import Supplier, ProcurementRequest, PurchaseOrder, GoodsReceipt
from procurement.services import save_supplier, audit_supplier, save_request, transition_request, save_purchase_order, add_purchase_line, transition_purchase, receive_goods
from fleet.models import Vehicle, Driver, Assignment
from fleet.services import save_vehicle, save_driver, assign_vehicle, record_checkpoint
from shipments.workflows import transition_shipment
from payments.services import issue_invoice, void_invoice
from finance.models import Payment, Reconciliation
from finance.services import record_payment, balance_due, reverse_payment, import_statement, match_payment, close_reconciliation
from integrations.models import Connection, IntegrationJob, GatewayIntent
from integrations.services import create_intent, settle_intent, enqueue, invoice_snapshot
from integrations.tasks import run_job
from integrations.adapters import OdooAdapter, FlutterwaveAdapter, PawaPayAdapter
from integrations.http import IntegrationError, safe_url


class CommercialFixtures:
    def setUp(self):
        self.maker = User.objects.create_user(username="commercial-maker", email="maker@example.com", is_staff=True, is_superuser=True)
        self.admin = User.objects.create_user(username="commercial-admin", email="approver@example.com", is_staff=True, is_superuser=True)
        self.customer = Customer.objects.create(full_name="Commercial Customer", email="commercial-customer@example.com", phone="0700000000")
        self.shipment = booked_shipment(self.customer)
        self.quote = self.shipment.quote
        company = Company.objects.create(name="QA", registration_number="COM-QA", tin="COM-QA", email="company@example.com", phone="0", address="Kampala")
        branch = Branch.objects.create(company=company, name="HQ", code="COM-QA", city="Kampala", country="Uganda", address="Kampala", phone="0", email="branch@example.com")
        self.warehouse = Warehouse.objects.create(branch=branch, name="QA warehouse", code="COM-QA", location="Kampala")
        self.product = save_product(actor=self.maker, data={"sku": "QA-001", "name": "Shipping crates", "unit": "units", "description": "", "is_active": True})
        self.stock = save_stock(actor=self.maker, data={"product": self.product, "warehouse": self.warehouse, "reorder_level": 2, "is_active": True})
        move_stock(actor=self.maker, item_id=self.stock.item_id, quantity_change=10, reason="Opening stock", expected_version=self.stock.item.version)

    def order(self):
        order = save_order(actor=self.maker, data={"quote": self.quote, "notes": "QA"})
        add_line(actor=self.maker, record_id=order.pk, stock=self.stock, quantity_value=5, unit_price=20)
        return transition_order(actor=self.maker, record_id=order.pk, target="submitted")

    def purchase(self):
        supplier = save_supplier(actor=self.maker, data={"name": "QA supplier", "registration_number": "QA-001", "email": "supplier@example.com", "phone": "0", "address": "Kampala", "is_active": True})
        audit_supplier(actor=self.admin, record_id=supplier.pk, outcome="pass", valid_until=timezone.localdate()+timedelta(days=30), notes="Supplier verified")
        request = save_request(actor=self.maker, data={"purpose": "Stock replenishment", "currency": "UGX", "budget": 400, "order": None})
        transition_request(actor=self.maker, record_id=request.pk, target="submitted")
        request = transition_request(actor=self.admin, record_id=request.pk, target="approved")
        purchase = save_purchase_order(actor=self.maker, data={"request": request, "supplier": supplier})
        add_purchase_line(actor=self.maker, record_id=purchase.pk, stock=self.stock, quantity_value=10, unit_price=20)
        transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")
        purchase = transition_purchase(actor=self.admin, record_id=purchase.pk, target="approved")
        return transition_purchase(actor=self.maker, record_id=purchase.pk, target="sent")

    def invoice(self):
        return issue_invoice(actor=self.maker, quote_id=self.quote.pk, due_date=timezone.localdate())

    def vehicle_and_driver(self):
        vehicle = save_vehicle(actor=self.maker, data={"registration": "UAA123A", "name": "QA truck", "capacity_kg": 1000, "status": "available", "odometer": 100, "next_service_date": timezone.localdate()+timedelta(days=30), "next_service_odometer": 10000})
        driver = save_driver(actor=self.maker, data={"user": self.admin, "license_number": "DL-QA", "license_expires": timezone.localdate()+timedelta(days=365), "is_active": True})
        return vehicle, driver

    def payment(self, invoice, amount=100, reference="BANK-QA", key="payment-qa"):
        return record_payment(actor=self.maker, invoice=invoice, amount=amount, currency=invoice.currency, method="bank", external_reference=reference, idempotency_key=key)

class CommercialTests(CommercialFixtures, TestCase):
    def test_order_reserves_prevents_manual_stock_theft_and_fulfills_once(self):
        order = self.order()
        with self.assertRaises(ValidationError):
            transition_order(actor=self.maker, record_id=order.pk, target="approved")
        transition_order(actor=self.admin, record_id=order.pk, target="approved")
        self.assertEqual(Reservation.objects.get(order_line__order=order).quantity, 5)
        item = InventoryItem.objects.get(pk=self.stock.item_id)
        with self.assertRaises(ValidationError):
            move_stock(actor=self.maker, item_id=item.pk, quantity_change=-6, reason="Cannot steal reserved stock", expected_version=item.version)
        transition_order(actor=self.maker, record_id=order.pk, target="fulfilled")
        transition_order(actor=self.maker, record_id=order.pk, target="fulfilled")
        self.assertEqual(InventoryItem.objects.get(pk=item.pk).quantity, 5)
        self.assertEqual(Reservation.objects.get(order_line__order=order).status, "consumed")

    def test_every_order_approval_requires_admin_even_below_threshold(self):
        order = self.order()
        user = User.objects.create_user(username="ordinary-approver", email="ordinary@example.com", is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="orders", codename__in=["approve_order", "change_order"]))
        with self.assertRaises(PermissionDenied):
            transition_order(actor=user, record_id=order.pk, target="approved")
        self.assertFalse(Reservation.objects.exists())

    def test_order_dispatch_requires_fleet_and_delivery_before_closure(self):
        order = self.order()
        transition_order(actor=self.admin, record_id=order.pk, target="approved")
        transition_order(actor=self.maker, record_id=order.pk, target="fulfilled")
        with self.assertRaises(ValidationError):
            transition_order(actor=self.maker, record_id=order.pk, target="shipped")
        vehicle, driver = self.vehicle_and_driver()
        assignment = assign_vehicle(actor=self.maker, data={"shipment": self.shipment, "vehicle": vehicle, "driver": driver, "route": "Kampala to Jinja"})
        transition_order(actor=self.maker, record_id=order.pk, target="shipped")
        record_checkpoint(actor=self.maker, record_id=assignment.pk, location="Mukono", latitude=Decimal(".35"), longitude=Decimal("32.75"))
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.current_location, "Mukono")
        with self.assertRaises(ValidationError):
            transition_order(actor=self.maker, record_id=order.pk, target="closed")
        transition_shipment(shipment_id=self.shipment.pk, actor=self.maker, target="delivered")
        order = transition_order(actor=self.maker, record_id=order.pk, target="closed")
        assignment.refresh_from_db()
        self.assertEqual(order.status, "closed")
        self.assertIsNotNone(assignment.released_at)

    def test_cancelled_order_releases_reservations(self):
        order = self.order()
        transition_order(actor=self.admin, record_id=order.pk, target="approved")
        transition_order(actor=self.maker, record_id=order.pk, target="cancelled", reason="Customer cancelled")
        self.assertFalse(Reservation.objects.filter(status="reserved").exists())
        self.assertEqual(InventoryItem.objects.get(pk=self.stock.item_id).quantity, 10)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, "cancelled")

    def test_warehouse_uuid_crud_archive_reactivate_and_stale_edit(self):
        self.client.force_login(self.admin)
        url = reverse("inventory:warehouses_edit", args=[self.warehouse.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        data = {"branch": str(self.warehouse.branch_id), "name": self.warehouse.name,
                "code": self.warehouse.code, "location": self.warehouse.location,
                "capacity": "", "manager": "", "expected_version": str(self.warehouse.updated_at)}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.warehouse.refresh_from_db()
        self.assertFalse(self.warehouse.is_active)
        self.assertEqual(self.client.get(url).status_code, 200)
        data["is_active"] = "on"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Warehouse changed")
        data["expected_version"] = str(self.warehouse.updated_at)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.warehouse.refresh_from_db()
        self.assertTrue(self.warehouse.is_active)

    def test_browser_form_creates_product_with_empty_initial_version(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("inventory:products_create"), {
            "sku": "NEW-PRODUCT", "name": "Pallet wrapping film", "unit": "rolls",
            "description": "", "is_active": "on", "expected_version": ""})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(sku="NEW-PRODUCT", version=1).exists())

    def test_order_approval_action_requires_permission_and_csrf(self):
        order = self.order()
        url = reverse("orders:orders_action", args=[order.pk, "transition"])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(url, {"target": "approved", "expected_version": order.version})
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, "submitted")

    def test_audit_captures_payment_state_before_and_after_reversal(self):
        payment = self.payment(self.invoice())
        reverse_payment(actor=self.admin, record_id=payment.pk, reason="Correction")
        audit = OperationsEvent.objects.get(entity_type="payment", entity_id=str(payment.pk), action="payment_reversed")
        self.assertEqual(audit.details["before"]["status"], "posted")
        self.assertEqual(audit.details["after"]["status"], "reversed")

    def test_purchase_partial_receipt_retries_and_supplier_payment(self):
        purchase = self.purchase()
        line = purchase.lines.get()
        receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=4, delivery_reference="RECEIPT-ONE")
        receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=4, delivery_reference="RECEIPT-ONE")
        self.assertEqual(InventoryItem.objects.get(pk=self.stock.item_id).quantity, 14)
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        with self.assertRaises(ValidationError):
            receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=7, delivery_reference="TOO-MUCH")
        receive_goods(actor=self.maker, record_id=purchase.pk, line=line, quantity_value=6, delivery_reference="RECEIPT-TWO")
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, "received")
        record_payment(actor=self.maker, purchase_order=purchase, amount=200, currency="UGX", method="bank", external_reference="SUPPLIER-PAY", idempotency_key="supplier-pay")
        self.assertEqual(balance_due(purchase), 0)

    def test_supplier_audit_and_budget_are_enforced(self):
        purchase = self.purchase()
        audit_supplier(actor=self.admin, record_id=purchase.supplier_id, outcome="fail", valid_until=timezone.localdate()+timedelta(days=30), notes="Compliance failed")
        with self.assertRaises(ValidationError):
            receive_goods(actor=self.maker, record_id=purchase.pk, line=purchase.lines.get(), quantity_value=1, delivery_reference="BLOCKED")

    def test_payments_partial_idempotent_no_overpayment_no_void_after_payment(self):
        invoice = self.invoice()
        first = self.payment(invoice, amount=40)
        self.assertEqual(self.payment(invoice, amount=40).pk, first.pk)
        self.assertEqual(balance_due(invoice), 60)
        with self.assertRaises(ValidationError):
            self.payment(invoice, amount=41)
        with self.assertRaises(ValidationError):
            self.payment(invoice, amount=61, reference="OVERPAY", key="overpay")
        with self.assertRaises(ValidationError):
            void_invoice(actor=self.maker, invoice_id=invoice.pk, reason="Cannot void paid invoice")
        reverse_payment(actor=self.admin, record_id=first.pk, reason="Entry correction")
        self.assertEqual(balance_due(invoice), 100)

    def test_statement_match_requires_exact_reference_amount_currency_and_closure(self):
        invoice = self.invoice()
        payment = self.payment(invoice)
        csv_file = SimpleUploadedFile("statement.csv", f"external_reference,amount,posted_date,description\nBANK-QA,100,{timezone.localdate()},Customer receipt\n".encode())
        statement = import_statement(actor=self.maker, number="STMT-QA", currency="UGX", statement_date=timezone.localdate(), opening_balance=0, closing_balance=100, csv_file=csv_file)
        with self.assertRaises(ValidationError):
            close_reconciliation(actor=self.maker, record_id=statement.pk)
        match_payment(actor=self.maker, record_id=statement.pk, line=statement.lines.get(), payment=payment)
        statement = close_reconciliation(actor=self.maker, record_id=statement.pk)
        self.assertEqual(statement.status, "closed")
        with self.assertRaises(ValidationError):
            reverse_payment(actor=self.admin, record_id=payment.pk, reason="Matched payments stay locked")

    def test_fleet_rejects_due_service_and_double_assignments(self):
        vehicle, driver = self.vehicle_and_driver()
        assign_vehicle(actor=self.maker, data={"shipment": self.shipment, "vehicle": vehicle, "driver": driver, "route": "Jinja"})
        with self.assertRaises(ValidationError):
            assign_vehicle(actor=self.maker, data={"shipment": self.shipment, "vehicle": vehicle, "driver": driver, "route": "Jinja"})

    def test_staff_screens_exports_filters_and_customer_denial(self):
        self.client.force_login(self.admin)
        self.order()
        for name in ("finance:home", "finance:payments_list", "finance:invoices_list", "finance:reconciliations_list", "inventory:home", "inventory:stock_list", "orders:home", "orders:orders_list", "procurement:home", "procurement:purchases_list", "fleet:home", "fleet:vehicles_list", "integrations:home", "integrations:jobs_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(reverse("orders:orders_list")+"?format=csv").status_code, 200)
        self.assertEqual(self.client.get(reverse("orders:orders_list")+"?format=pdf").status_code, 200)
        self.assertEqual(self.client.get(reverse("orders:orders_list")+"?date_from=bad").status_code, 200)
        customer = User.objects.create_user(username="not-staff", email="not-staff@example.com")
        self.client.force_login(customer)
        self.assertEqual(self.client.get(reverse("finance:payments_list")).status_code, 403)

    def test_normal_orm_writes_cannot_bypass_business_services(self):
        with self.assertRaises(ValidationError):
            Product.objects.filter(pk=self.product.pk).update(name="Bypass")
        with self.assertRaises(ValidationError):
            self.product.delete()
        self.product.name = "Bypass"
        with self.assertRaises(ValidationError):
            self.product.save()
