from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from .models import ContactMessage


class ManagementAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="access", email="access@example.com", is_staff=True)
        self.message = ContactMessage.objects.create(name="Amina", email="amina@example.com", subject="Delivery", message="Hello")
        self.endpoints = [
            (name, []) for name in ("dashboard", "customer_list", "customer_create", "quotation_list", "quotation_create",
                "shipment_list", "shipment_create", "service_list", "service_create", "carrier_list", "carrier_create", "contact_message_list")
        ] + [(name, [999999]) for name in ("customer_update", "quotation_update", "shipment_update", "service_update", "carrier_update")]
        self.endpoints.append(("contact_message_read", [self.message.pk]))

    def test_anonymous_users_are_redirected_to_login(self):
        for name, args in self.endpoints:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("login") + "?next="))

    def test_nonstaff_users_are_denied_even_with_model_permissions(self):
        self.user.is_staff = False
        self.user.save()
        self.user.user_permissions.add(*Permission.objects.all())
        self.client.force_login(self.user)
        for name, args in self.endpoints:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
                self.assertEqual(self.client.post(reverse(name, args=args), {}).status_code, 403)

    def test_staff_without_permissions_cannot_read_or_write_business_records(self):
        self.client.force_login(self.user)
        for name, args in self.endpoints[1:]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
                self.assertEqual(self.client.post(reverse(name, args=args), {}).status_code, 403)

    def test_view_only_staff_can_list_but_cannot_create_or_edit(self):
        self.user.user_permissions.add(*Permission.objects.filter(codename__startswith="view_"))
        self.client.force_login(self.user)
        for resource in ("customer", "quotation", "shipment", "service", "carrier"):
            with self.subTest(resource=resource):
                response = self.client.get(reverse(resource + "_list"))
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context["create_url"])
                self.assertEqual(self.client.post(reverse(resource + "_create"), {}).status_code, 403)
                self.assertEqual(self.client.post(reverse(resource + "_update", args=[999999]), {}).status_code, 403)

    def test_message_get_has_no_side_effect_and_post_requires_change_permission(self):
        self.user.user_permissions.add(Permission.objects.get(codename="view_contactmessage"))
        self.client.force_login(self.user)
        url = reverse("contact_message_read", args=[self.message.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.message.refresh_from_db()
        self.assertFalse(self.message.is_read)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="change_contactmessage"))
        self.assertRedirects(self.client.post(url), url)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_read)

    def test_message_post_requires_csrf_token(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="core"))
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse("contact_message_read", args=[self.message.pk]))
        self.assertEqual(response.status_code, 403)
        self.message.refresh_from_db()
        self.assertFalse(self.message.is_read)

    def test_missing_service_and_carrier_return_404(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="logistics"))
        self.client.force_login(self.user)
        for resource in ("service", "carrier"):
            self.assertEqual(self.client.get(reverse(resource + "_update", args=[999999])).status_code, 404)
