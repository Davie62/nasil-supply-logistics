"""Shared staff, organization and catalogue fixtures for the commercial suites.

Only records are created here; every test exercises the workflow service under
test. Keeping this setup in one place avoids five copies of the same fixtures
and keeps the per-app suites focused on behaviour.
"""
from django.contrib.auth.models import Permission

from accounts.models import User
from core.test_helpers import booked_shipment
from customers.models import Customer
from inventory.services import save_product, save_stock
from operations.models import InventoryItem
from operations.services import move_stock
from organization.models import Branch, Company, Department, Warehouse

# The maker represents an ordinary staff operator with explicit grants. The
# approver is a superuser so approval separation and administrator-only rules
# are exercised against a different person, never against the maker.
FIXTURE_PERMISSIONS = (
    # Catalogue and stock.
    "add_product", "change_product", "add_stocklevel", "change_stocklevel",
    "add_warehouse", "change_warehouse", "view_stocklevel",
    "add_inventoryitem", "change_inventoryitem", "adjust_inventory",
    # Quotations, orders and shipments.
    "view_quote", "add_order", "change_order", "fulfill_order",
    "view_shipment", "change_shipment", "add_shipment",
    # Procurement.
    "add_supplier", "change_supplier", "add_supplieraudit",
    "add_procurementrequest", "change_procurementrequest",
    "add_purchaseorder", "change_purchaseorder", "receive_purchaseorder",
    # Fleet.
    "add_vehicle", "change_vehicle", "add_driver", "change_driver",
    "add_assignment", "change_assignment", "add_routecheckpoint",
    "add_maintenance", "change_maintenance",
    # Finance.
    "add_payment", "reverse_payment", "add_reconciliation",
    "change_reconciliation", "add_invoice", "change_invoice",
)


class CommercialFixtureMixin:
    """Creates two staff operators plus a stocked warehouse and approved quote."""

    def setUp(self):
        self.maker = User.objects.create_user(
            username="commercial-maker", email="maker@example.com", is_staff=True,
        )
        self.approver = User.objects.create_user(
            username="commercial-approver", email="approver@example.com",
            is_staff=True, is_superuser=True,
        )
        self.outsider = User.objects.create_user(
            username="commercial-outsider", email="outsider@example.com", is_staff=True,
        )
        self.maker.user_permissions.add(
            *Permission.objects.filter(codename__in=FIXTURE_PERMISSIONS)
        )

        self.customer = Customer.objects.create(
            full_name="Commercial Customer", email="commercial-customer@example.com",
            phone="0700000000",
        )
        # booked_shipment creates an approved quotation and its pending shipment.
        self.shipment = booked_shipment(self.customer)
        self.quote = self.shipment.quote

        company = Company.objects.create(
            name="QA Company", registration_number="COM-QA", tin="COM-QA",
            email="company@example.com", phone="0", address="Kampala",
        )
        self.branch = Branch.objects.create(
            company=company, name="HQ", code="COM-QA", city="Kampala",
            country="Uganda", address="Kampala", phone="0", email="branch@example.com",
        )
        self.department = Department.objects.create(
            branch=self.branch, name="Operations", code="COM-OPS",
        )
        self.warehouse = Warehouse.objects.create(
            branch=self.branch, name="QA warehouse", code="COM-WH", location="Kampala",
        )
        self.product = save_product(actor=self.maker, data={
            "sku": "QA-001", "name": "Shipping crates", "unit": "units",
            "description": "", "is_active": True,
        })
        self.stock = save_stock(actor=self.maker, data={
            "product": self.product, "warehouse": self.warehouse,
            "reorder_level": 2, "is_active": True,
        })
        self.item = InventoryItem.objects.get(pk=self.stock.item_id)
        move_stock(
            actor=self.maker, item_id=self.item.pk, quantity_change=10,
            reason="Opening stock", expected_version=self.item.version,
        )

    def refreshed_item(self):
        return InventoryItem.objects.get(pk=self.item.pk)
