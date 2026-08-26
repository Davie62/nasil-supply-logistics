from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


@override_settings(SECURE_SSL_REDIRECT=False)
class AuthenticationSecurityTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="security-user",
			email="security@example.com",
			password="Strong-password-123",
		)

	def test_logout_requires_post(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("logout"))
		self.assertEqual(response.status_code, 405)
		self.assertTrue(response.wsgi_request.user.is_authenticated)

	def test_repeated_failed_logins_lock_account(self):
		for _ in range(5):
			response = self.client.post(reverse("login"), {
				"username": self.user.username,
				"password": "incorrect-password",
			})
			self.assertEqual(response.status_code, 200)

		self.user.refresh_from_db()
		self.assertEqual(self.user.failed_login_attempts, 5)
		self.assertIsNotNone(self.user.locked_until)

		response = self.client.post(reverse("login"), {
			"username": self.user.username,
			"password": "Strong-password-123",
		})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.wsgi_request.user.is_authenticated)
