from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import ContactMessage
from customers.models import Customer
from quotations.models import Quote


class PublicSubmissionTests(TestCase):
    def setUp(self):
        self.quote_data = {
            "full_name": "Amina Namusoke", "company_name": "Amina Foods",
            "email": "AMINA@example.com", "phone": "+256700000001",
            "pickup_location": "Kampala", "destination": "Jinja",
            "cargo_description": "Food", "weight": "12.50",
        }
        self.contact_data = {"name": "Amina", "lastname": "Namusoke",
                             "email": "AMINA@example.com", "subject": "Delivery", "message": "Please call me."}

    def test_valid_quote_is_pending_and_reuses_normalized_customer(self):
        customer = Customer.objects.create(full_name="Existing contact", email="amina@example.com", phone="0700000000")
        data = {**self.quote_data, "status": "approved", "customer": "99999"}
        self.assertRedirects(self.client.post(reverse("quote"), data), reverse("quote"))
        quotation = Quote.objects.get()
        self.assertEqual(quotation.customer, customer)
        self.assertEqual(quotation.status, "pending")
        self.assertEqual(Customer.objects.count(), 1)
        customer.refresh_from_db()
        self.assertEqual(customer.full_name, "Existing contact")

    def test_invalid_weights_show_errors_and_write_nothing(self):
        for weight in ("", "0", "-1", "NaN", "Infinity", "abc", "100000000000000", "1.001"):
            with self.subTest(weight=weight):
                response = self.client.post(reverse("quote"), {**self.quote_data, "weight": weight})
                self.assertEqual(response.status_code, 200)
                self.assertIn("weight", response.context["form"].errors)
                self.assertContains(response, "Amina Namusoke")
                self.assertFalse(Customer.objects.exists())
                self.assertFalse(Quote.objects.exists())

    def test_invalid_quote_contacts_and_missing_cargo_are_rejected(self):
        for field, value in (("email", "invalid"), ("full_name", " "), ("phone", ""), ("phone", "x" * 21), ("cargo_description", "")):
            with self.subTest(field=field):
                response = self.client.post(reverse("quote"), {**self.quote_data, field: value})
                self.assertIn(field, response.context["form"].errors)
                self.assertFalse(Customer.objects.exists())

    def test_quote_failure_rolls_back_new_customer(self):
        with patch("quotations.models.Quote.save", side_effect=IntegrityError("simulated write failure")):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse("quote"), self.quote_data)
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(Quote.objects.exists())

    def test_contact_is_validated_and_preserves_full_name(self):
        self.assertRedirects(self.client.post(reverse("contact"), self.contact_data), reverse("contact"))
        message = ContactMessage.objects.get()
        self.assertEqual(message.name, "Amina Namusoke")
        self.assertEqual(message.email, "amina@example.com")
        for field, value in (("email", "invalid"), ("subject", " "), ("message", ""), ("name", "x" * 256)):
            with self.subTest(field=field):
                response = self.client.post(reverse("contact"), {**self.contact_data, field: value})
                self.assertIn(field, response.context["form"].errors)
        self.assertEqual(ContactMessage.objects.count(), 1)
