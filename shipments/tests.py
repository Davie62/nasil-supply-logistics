from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from customers.models import Customer
from quotations.models import Quote
from .models import Shipment
from core.test_helpers import booked_shipment


class ShipmentWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="shipment-user", password="Strong-password-123", is_staff=True)
        customer = Customer.objects.create(full_name="Shipment Customer", email="shipment@example.com", phone="+256700000003")
        self.shipment = booked_shipment(customer)
        self.quote = self.shipment.quote
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="shipments", content_type__model="shipment"))
        self.user.user_permissions.add(Permission.objects.get(codename="view_quote"))
        self.client.force_login(self.user)

    def test_update_shipment(self):
        shipment = self.shipment
        response = self.client.post(reverse("shipment_update", args=[shipment.pk]), {
            "record_version": shipment.version,
            "quote": self.quote.pk, "carrier": "", "current_location": "Jinja",
            "estimated_delivery": (date.today() + timedelta(days=3)).isoformat(), "status": "in_transit",
        })
        self.assertRedirects(response, reverse("shipment_list"))
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, "in_transit")

    # Create your tests here.

# Create your tests here.
