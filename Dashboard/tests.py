from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.models import User


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardModuleTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="dashboard-user",
			email="dashboard@example.com",
			password="Strong-password-123",
		)

	def test_modules_require_authentication(self):
		for module in ("shipments", "quotations", "employees", "reports", "settings"):
			response = self.client.get(reverse(f"dashboard_{module}"))
			self.assertRedirects(response, f"/accounts/login/?next=/dashboard/{module}/")

	def test_modules_render_for_authenticated_user(self):
		self.client.force_login(self.user)
		for module in ("shipments", "quotations", "employees", "reports", "settings"):
			response = self.client.get(reverse(f"dashboard_{module}"))
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, response.context["title"])

	def test_payments_is_not_enabled(self):
		with self.assertRaises(NoReverseMatch):
			reverse("payments")
