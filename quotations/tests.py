from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from customers.models import Customer
from .models import Quote


class QuotationWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="quote-user", password="Strong-password-123", is_staff=True)
        self.customer = Customer.objects.create(full_name="Quote Customer", email="quote@example.com", phone="+256700000002")
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="quotations", content_type__model="quote"))
        self.client.force_login(self.user)

    def test_create_and_update_quotation(self):
        response = self.client.post(reverse("quotation_create"), {
            "customer": self.customer.pk, "service": "", "pickup_location": "Kampala",
            "destination": "Mbarara", "transport_mode": "Road", "cargo_description": "Food",
            "weight": "100.00", "cargo_value": "500000", "special_instructions": "", "status": "pending",
        })
        self.assertRedirects(response, reverse("quotation_list"))
        quote = Quote.objects.get(customer=self.customer)
        response = self.client.post(reverse("quotation_update", args=[quote.pk]), {
            "record_version": quote.version,
            "customer": self.customer.pk, "service": "", "pickup_location": quote.pickup_location,
            "destination": quote.destination, "transport_mode": "Road", "cargo_description": "Food",
            "weight": "100.00", "cargo_value": "500000", "special_instructions": "", "status": "approved",
        })
        self.assertRedirects(response, reverse("quotation_list"))
        quote.refresh_from_db()
        # Posting an approval through the details form must not approve it.
        self.assertEqual(quote.status, "pending")

    # Create your tests here.

# Create your tests here.
