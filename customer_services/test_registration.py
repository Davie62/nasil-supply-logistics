from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounts.models import User
from customers.models import Customer
from core.test_helpers import booked_shipment
from operations.models import OperationsEvent
from .models import CustomerAccess, CustomerNotification, RegistrationVerification
from .registration import register_customer, complete_registration, resend_code, verification_delivery_allowed
from .notifications import render_delivery
from .tasks import deliver_notification


@override_settings(DEBUG=True, NOTIFICATIONS_DELIVERY_ENABLED=False)
class RegistrationTests(TestCase):
    def data(self, **changes):
        return {"full_name": "New Customer", "email": "new-customer@example.com", "phone": "+256700000009", "company_name": "New Trading",
                "username": "new-customer", "password": "Strong-registration-password-2026!", **changes}

    def form_data(self):
        data = self.data()
        password = data.pop("password")
        return {**data, "password1": password, "password2": password}

    def test_new_registration_requires_code_before_access(self):
        verification, code = register_customer(**self.data())
        user = verification.user
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_verified)
        self.assertFalse(CustomerAccess.objects.filter(user=user).exists())
        self.assertEqual(user.groups.count(), 0)
        self.assertNotEqual(verification.code_hash, code)
        access = complete_registration(verification_id=verification.pk, code=code)
        access.user.refresh_from_db()
        self.assertTrue(access.user.is_verified)
        self.assertEqual(access.customer.email, self.data()["email"])
        self.assertTrue(OperationsEvent.objects.filter(action="registration_verified").exists())
        self.assertEqual(CustomerNotification.objects.get(kind="registration_verification").payload, {})
        with self.assertRaises(ValidationError):
            complete_registration(verification_id=verification.pk, code=code)

    def test_existing_customer_records_are_not_claimed_until_verified(self):
        customer = Customer.objects.create(full_name="Existing Customer", email=self.data()["email"], phone="0700000000")
        shipment = booked_shipment(customer)
        verification, code = register_customer(**self.data())
        self.assertEqual(verification.customer_id, customer.pk)
        self.client.force_login(verification.user)
        self.assertEqual(self.client.get(reverse("portal_shipment", args=[shipment.pk])).status_code, 403)
        customer.refresh_from_db()
        self.assertEqual(customer.full_name, "Existing Customer")
        complete_registration(verification_id=verification.pk, code=code)
        self.assertEqual(self.client.get(reverse("portal_shipment", args=[shipment.pk])).status_code, 200)

    def test_existing_staff_email_is_rejected_without_mutation(self):
        staff = User.objects.create_user(username="admin", email=self.data()["email"], is_staff=True, is_superuser=True)
        with self.assertRaises(ValidationError):
            register_customer(**self.data())
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(RegistrationVerification.objects.exists())
        self.assertFalse(Customer.objects.exists())
        staff.refresh_from_db()
        self.assertTrue(staff.is_superuser)

    def test_invalid_codes_commit_attempt_limit_and_expiry(self):
        verification, code = register_customer(**self.data())
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            with self.assertRaises(ValidationError):
                complete_registration(verification_id=verification.pk, code=wrong)
        verification.refresh_from_db()
        self.assertEqual(verification.attempts, 5)
        with self.assertRaises(ValidationError):
            complete_registration(verification_id=verification.pk, code=code)
        RegistrationVerification.objects.filter(pk=verification.pk).update(attempts=0, expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            complete_registration(verification_id=verification.pk, code=code)

    def test_resend_rotates_code_and_blocks_stale_delivery(self):
        verification, original_code = register_customer(**self.data())
        original_notification = CustomerNotification.objects.get(kind="registration_verification")
        with self.assertRaises(ValidationError):
            resend_code(verification_id=verification.pk)
        RegistrationVerification.objects.filter(pk=verification.pk).update(sent_at=timezone.now()-timedelta(minutes=2))
        new_code = resend_code(verification_id=verification.pk)
        self.assertFalse(verification_delivery_allowed(original_notification))
        with self.assertRaises(ValidationError):
            complete_registration(verification_id=verification.pk, code=original_code if original_code != new_code else "invalid")
        self.assertIsNotNone(complete_registration(verification_id=verification.pk, code=new_code))

    def test_http_signup_verify_and_login_resumption(self):
        response = self.client.post(reverse("portal_register"), self.form_data())
        self.assertRedirects(response, reverse("portal_verify_email"))
        self.assertNotIn("_auth_user_id", self.client.session)
        code = self.client.session["registration_code_preview"]
        self.assertContains(self.client.get(reverse("portal_verify_email")), "Local development preview")
        self.client = Client()
        response = self.client.post(reverse("portal_login"), {"username": self.data()["username"], "password": self.data()["password"]})
        self.assertRedirects(response, reverse("portal_verify_email"))
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("portal_verify_email"), {"code": code})
        self.assertRedirects(response, reverse("portal_dashboard"))
        self.assertNotIn("registration_id", self.client.session)
        self.assertNotIn("registration_code_preview", self.client.session)
        self.assertTrue(CustomerAccess.objects.exists())

    def test_verification_requires_own_registration_session_and_csrf(self):
        verification, code = register_customer(**self.data())
        self.assertRedirects(self.client.post(reverse("portal_verify_email"), {"code": code}), reverse("portal_register"))
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("portal_register"), self.form_data()).status_code, 403)
        self.assertFalse(CustomerAccess.objects.exists())

    def test_email_owner_can_recover_an_unverified_registration(self):
        from .notifications import recipient_for
        verification, code = register_customer(**self.data())
        response = self.client.post(reverse("portal_password_reset"), {"email": verification.user.email})
        self.assertEqual(response.status_code, 302)
        notification = CustomerNotification.objects.get(kind="password_reset")
        self.assertEqual(notification.recipient, verification.user.email)
        self.assertIn(verification.user.username, notification.body)
        self.assertEqual(recipient_for(verification.customer, "password_reset"), ("email", verification.user.email, ""))
        self.assertFalse(CustomerAccess.objects.exists())

    def test_provider_uses_code_email_and_removes_payload_after_acceptance(self):
        verification, code = register_customer(**self.data())
        notification = CustomerNotification.objects.get(kind="registration_verification")
        text, html, sms = render_delivery(notification)
        self.assertIn(code, text)
        self.assertIn(code, html)
        self.assertEqual(sms, "")
        self.assertTrue(verification_delivery_allowed(notification))
        with override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True), patch("customer_services.providers.sendgrid", return_value="SG-test"):
            self.assertEqual(deliver_notification.apply(args=[notification.pk], throw=True).get(), "sent")
        notification.refresh_from_db()
        self.assertEqual(notification.payload, {})

    @override_settings(DEBUG=False)
    def test_production_never_shows_local_code_or_creates_undeliverable_registration(self):
        with self.assertRaises(ValidationError):
            register_customer(**self.data())
        self.assertFalse(User.objects.exists())
        self.assertFalse(Customer.objects.exists())

    def test_registration_throttles_and_password_validation(self):
        data = self.form_data()
        data.update(password1="123", password2="123")
        self.assertContains(self.client.post(reverse("portal_register"), data), "too short")
        self.assertFalse(User.objects.exists())
        with patch("customer_services.registration_views.allow_request", return_value=False):
            self.assertEqual(self.client.post(reverse("portal_register"), self.form_data()).status_code, 429)
