from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from .models import Customer


class CustomerWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="customer-user", password="Strong-password-123", is_staff=True)
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="customers", content_type__model="customer"))
        self.client.force_login(self.user)

    def test_create_and_update_customer(self):
        response = self.client.post(reverse("customer_create"), {
            "full_name": "Amina Namusoke", "company_name": "Amina Foods",
            "email": "amina@example.com", "phone": "+256700000001",
            "address": "Kampala", "city": "Kampala", "country": "Uganda",
        })
        self.assertRedirects(response, reverse("customer_list"))
        customer = Customer.objects.get(email="amina@example.com")
        response = self.client.post(reverse("customer_update", args=[customer.pk]), {
            "full_name": "Amina N. Namusoke", "company_name": "Amina Foods",
            "email": customer.email, "phone": customer.phone,
            "address": "Kampala", "city": "Kampala", "country": "Uganda",
        })
        self.assertRedirects(response, reverse("customer_list"))
        customer.refresh_from_db()
        self.assertEqual(customer.full_name, "Amina N. Namusoke")

    # Create your tests here.

# Create your tests here.
