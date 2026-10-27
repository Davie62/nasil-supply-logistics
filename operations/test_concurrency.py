from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from accounts.models import User
from organization.models import Company, Branch, Warehouse
from .services import move_stock, save_inventory


@skipUnlessDBFeature("has_select_for_update")
class InventoryConcurrencyTests(TransactionTestCase):
    def test_concurrent_issues_cannot_oversell_or_reuse_a_stale_version(self):
        company = Company.objects.create(name="QA", registration_number="STOCK-RACE", tin="STOCK-RACE", email="race@example.com", phone="0", address="Kampala")
        branch = Branch.objects.create(company=company, name="QA", code="RACE", city="Kampala", country="Uganda", address="QA", phone="0", email="race-branch@example.com")
        warehouse = Warehouse.objects.create(branch=branch, name="QA", code="RACE", location="Kampala")
        actor = User.objects.create_user(username="stock-race", email="stock-race@example.com", is_staff=True, is_superuser=True)
        item = save_inventory(actor=actor, data={"sku": "RACE", "name": "Stock", "warehouse": warehouse, "unit": "units", "reorder_level": 0, "is_active": True})
        move_stock(actor=actor, item_id=item.pk, quantity_change=5, reason="Opening receipt", expected_version=item.version)
        item.refresh_from_db()
        barrier = Barrier(2)

        def issue():
            close_old_connections()
            try:
                user = User.objects.get(pk=actor.pk)
                barrier.wait(timeout=10)
                try:
                    move_stock(actor=user, item_id=item.pk, quantity_change=-4, reason="Concurrent issue", expected_version=item.version)
                    return "issued"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(issue) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertCountEqual(results, ["issued", "rejected"])
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.movements.count(), 2)
