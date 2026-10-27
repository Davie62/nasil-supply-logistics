"""Run against PostgreSQL before production to exercise real row-lock behavior."""
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from .models import EmployeeIDSequence
from .services import EmployeeService


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock integration test")
class ConcurrentEmployeeIDTests(TransactionTestCase):
    def test_concurrent_allocations_are_unique_for_new_and_existing_year(self):
        def allocate(_):
            close_old_connections()
            try:
                return EmployeeService.generate_employee_id()
            finally:
                close_old_connections()
        for iteration in range(2):
            with self.subTest(iteration=iteration):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    identifiers = list(pool.map(allocate, range(8)))
                self.assertEqual(len(set(identifiers)), 8)
        self.assertEqual(EmployeeIDSequence.objects.get().last_number, 16)
