from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature

from accounts.models import User
from customers.models import Customer
from quotations.workflows import update_quote
from shipments.models import Shipment
from shipments.workflows import convert_quote_to_shipment
from .test_helpers import booked_shipment


@skipUnlessDBFeature("has_select_for_update")
@override_settings(QUOTATION_APPROVAL_THRESHOLDS={"UGX": "1000000", "USD": "1000"})
class WorkflowConcurrencyTests(TransactionTestCase):
    def setUp(self):
        customer = Customer.objects.create(full_name="Customer", email="race@example.com", phone="0700000000")
        self.shipment = booked_shipment(customer)
        self.actor_id = self.shipment.created_by_id
        self.quote_id = self.shipment.quote_id

    def concurrent(self, operation):
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.actor_id)
                barrier.wait(timeout=10)
                return operation(actor)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_conversion_retry_returns_one_booking(self):
        from quotations.workflows import create_quote, transition_quote
        actor = User.objects.get(pk=self.actor_id)
        approver = User.objects.get(username='fixture-approver')
        original = self.shipment.quote
        quote = create_quote(actor=actor, data={"customer": original.customer, "pickup_location": "A", "destination": "B", "cargo_description": "Goods", "weight": 1, "base_amount": 10, "valid_until": original.valid_until})
        transition_quote(quote_id=quote.pk, actor=actor, target='reviewed')
        transition_quote(quote_id=quote.pk, actor=approver, target='approved')
        results = self.concurrent(lambda actor: convert_quote_to_shipment(quote_id=quote.pk, actor=actor).pk)
        self.assertEqual(results[0], results[1])
        shipment = Shipment.objects.get(quote_id=quote.pk)
        self.assertEqual(shipment.history.count(), 1)

    def test_concurrent_edits_with_same_version_reject_stale_write(self):
        from quotations.workflows import create_quote
        customer = self.shipment.quote.customer
        actor = User.objects.get(pk=self.actor_id)
        quote = create_quote(actor=actor, data={"customer": customer, "pickup_location": "A", "destination": "B", "cargo_description": "Goods", "weight": 1})

        def edit(actor):
            try:
                update_quote(quote_id=quote.pk, actor=actor, data={"base_amount": 10}, expected_version=quote.version)
                return "saved"
            except ValidationError:
                return "stale"

        self.assertCountEqual(self.concurrent(edit), ["saved", "stale"])
