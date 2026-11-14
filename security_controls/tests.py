import json
import logging
import time
from datetime import timedelta
from unittest.mock import patch
import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.test import TestCase, SimpleTestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from .crypto import encrypt_secret, decrypt_secret, rotate_secret
from .events import security_event
from .logging import SafeJSONFormatter
from .mfa import verify_factor, mark_verified
from .models import MFAProfile, SecurityEvent, SecurityAlert
from .network import client_ip
from .validators import strict_json, clean_text


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], SECURE_SSL_REDIRECT=False)
class SecurityTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(username="security-admin", email="security-admin@example.com", password="Strong-security-password-2026!")

    def enroll(self, client=None):
        client = client or self.client
        client.force_login(self.staff)
        response = client.get(reverse("security_mfa_setup"))
        self.assertEqual(response.status_code, 200)
        encrypted = client.session["security_pending_secret"]
        secret = decrypt_secret(encrypted)
        response = client.post(reverse("security_mfa_setup"), {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(response, reverse("security_mfa_recovery"), fetch_redirect_response=False)
        codes = json.loads(decrypt_secret(client.session["security_recovery_codes"]))
        return secret, codes

    def test_lockout_cannot_be_bypassed_through_admin(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": self.staff.username, "password": "incorrect"})
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.failed_login_attempts, 5)
        self.assertIsNone(authenticate(username=self.staff.username, password="Strong-security-password-2026!"))
        response = self.client.post(reverse("admin:login"), {"username": self.staff.username, "password": "Strong-security-password-2026!", "next": "/admin/"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_authentication_resets_attempts(self):
        authenticate(username=self.staff.username, password="bad")
        self.assertIsNotNone(authenticate(username=self.staff.username, password="Strong-security-password-2026!"))
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.failed_login_attempts, 0)

    @override_settings(SECURITY_REQUIRE_STAFF_MFA=True)
    def test_mfa_gates_dashboard_admin_and_writes_before_enrollment(self):
        self.client.force_login(self.staff)
        for url in (reverse("dashboard"), reverse("admin:index"), reverse("inventory:products_create")):
            response = self.client.get(url)
            self.assertRedirects(response, reverse("security_mfa_setup"), fetch_redirect_response=False)
        from inventory.models import Product
        self.client.post(reverse("inventory:products_create"), {"sku": "MFA-BYPASS", "name": "Blocked", "unit": "units", "is_active": "on"})
        self.assertFalse(Product.objects.filter(sku="MFA-BYPASS").exists())

    @override_settings(SECURITY_REQUIRE_STAFF_MFA=True)
    def test_enrollment_encrypts_secret_hashes_codes_and_rotates_session(self):
        self.client.force_login(self.staff)
        original = self.client.session.session_key
        secret, codes = self.enroll()
        profile = MFAProfile.objects.get(user=self.staff)
        self.assertTrue(profile.enabled)
        self.assertNotIn(secret, profile.encrypted_secret)
        self.assertNotIn(codes[0], json.dumps(profile.recovery_hashes))
        self.assertNotEqual(original, self.client.session.session_key)
        self.assertEqual(self.client.get(reverse("security_mfa_qr")).status_code, 404)
        response = self.client.get(reverse("security_mfa_recovery"))
        self.assertContains(response, codes[0])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.client.post(reverse("security_mfa_recovery"))
        self.assertNotIn("security_recovery_codes", self.client.session)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_enabled_mfa_is_enforced_even_when_mandatory_enrollment_is_off(self):
        secret, codes = self.enroll()
        other = Client()
        other.force_login(self.staff)
        self.assertRedirects(other.get(reverse("dashboard")), reverse("security_mfa_challenge"), fetch_redirect_response=False)
        response = other.post(reverse("security_mfa_challenge"), {"code": codes[0]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(other.get(reverse("dashboard")).status_code, 200)
        self.assertIsNone(verify_factor(self.staff, codes[0]))
        self.assertTrue(SecurityAlert.objects.filter(code="mfa_recovery_used").exists())

    def test_totp_replay_is_rejected(self):
        secret, _ = self.enroll()
        self.assertIsNone(verify_factor(self.staff, pyotp.TOTP(secret).now()))

    def test_five_bad_second_factors_lock_verification(self):
        self.enroll()
        for _ in range(5):
            self.assertIsNone(verify_factor(self.staff, "invalid"))
        profile = MFAProfile.objects.get(user=self.staff)
        self.assertEqual(profile.failed_attempts, 5)
        self.assertGreater(profile.locked_until, timezone.now())

    def test_privilege_changes_require_fresh_mfa(self):
        self.enroll()
        permission = Permission.objects.get(content_type__app_label="core", codename="view_contactmessage")
        self.staff.user_permissions.add(permission)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("security_mfa_challenge"), fetch_redirect_response=False)
        self.assertTrue(SecurityEvent.objects.filter(code="privileges_changed", target_id=self.staff.pk).exists())

    def test_idle_and_absolute_session_expiration(self):
        for field, seconds in (("security_last_seen", settings.SECURITY_STAFF_IDLE_SECONDS), ("security_started_at", settings.SECURITY_STAFF_SESSION_SECONDS)):
            self.client.force_login(self.staff)
            session = self.client.session
            session[field] = int(time.time())-seconds-1
            session.save()
            self.assertRedirects(self.client.get(reverse("dashboard")), reverse("login"), fetch_redirect_response=False)
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_sign_out_all_devices_revokes_other_sessions(self):
        self.client.force_login(self.staff)
        other = Client()
        other.force_login(self.staff)
        response = self.client.post(reverse("security_account"), {"password": "Strong-security-password-2026!"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(other.get(reverse("dashboard")), reverse("login"), fetch_redirect_response=False)

    def test_csrf_still_required_for_mfa_and_business_actions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(reverse("security_mfa_setup"), {"code": "123456"}).status_code, 403)
        self.assertTrue(SecurityEvent.objects.filter(code="csrf_rejected").exists())

    def test_request_bounds_duplicate_keys_and_report_filter_allowlist(self):
        self.client.force_login(self.staff)
        for url in ("/finance/payments/?page=1&page=2", "/finance/payments/?page=-1", "/finance/payments/?q="+"x"*151, "/finance/payments/?unexpected=field", "/?name=%00"):
            self.assertEqual(self.client.get(url).status_code, 400, url)

    def test_sql_and_html_text_remain_data_and_render_escaped(self):
        self.client.force_login(self.staff)
        name = "<script>alert('x')</script>"
        response = self.client.post(reverse("inventory:products_create"), {"sku": "ESCAPED", "name": name, "unit": "units", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        detail = self.client.get(response.url)
        self.assertContains(detail, "&lt;script&gt;")
        self.assertNotContains(detail, name)
        self.assertEqual(self.client.get(reverse("inventory:products_list"), {"q": "' OR 1=1 --"}).status_code, 200)

    def test_csp_nonce_and_security_headers(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard"))
        nonce = response.wsgi_request.csp_nonce
        self.assertIn("'nonce-"+nonce+"'", response["Content-Security-Policy"])
        self.assertContains(response, f'nonce="{nonce}"')
        self.assertIn("object-src 'none'", response["Content-Security-Policy"])
        self.assertIn("X-Request-ID", response)

    def test_ip_throttling_ignores_untrusted_forwarded_headers(self):
        request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.2", HTTP_X_REAL_IP="198.51.100.3")
        self.assertEqual(client_ip(request), "203.0.113.2")
        with override_settings(SECURITY_TRUSTED_PROXY_NETWORKS=["127.0.0.1/32"]):
            request.META["REMOTE_ADDR"] = "127.0.0.1"
            self.assertEqual(client_ip(request), "198.51.100.3")

    def test_staff_login_and_public_forms_are_rate_limited(self):
        with patch("customer_services.security.allow_request", return_value=False):
            for name in ("login", "admin:login", "quote", "contact"):
                self.assertEqual(self.client.post(reverse(name), {}).status_code, 429)

    def test_repeated_failures_create_one_redacted_alert(self):
        request = RequestFactory().post("/?password=DO-NOT-LOG", {"password": "SECRET"}, REMOTE_ADDR="203.0.113.8")
        for _ in range(6):
            security_event("login_failed", request=request, level="warning")
        self.assertEqual(SecurityAlert.objects.filter(code="login_failed").count(), 1)
        self.assertNotIn("203.0.113.8", SecurityEvent.objects.first().ip_fingerprint)

    def test_event_storage_failure_does_not_poison_outer_transaction(self):
        with patch("security_controls.models.SecurityEvent.objects.create", side_effect=OperationalError("not available")):
            self.assertIsNone(security_event("test_event"))
        self.assertEqual(User.objects.count(), 1)


class SecurityUtilityTests(SimpleTestCase):
    def test_encryption_rotation_and_tamper_rejection(self):
        first, second = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        with override_settings(SECURITY_ENCRYPTION_KEYS=[first]):
            encrypted = encrypt_secret("test-sensitive-value")
            self.assertEqual(decrypt_secret(encrypted), "test-sensitive-value")
        with override_settings(SECURITY_ENCRYPTION_KEYS=[second, first]):
            rotated = rotate_secret(encrypted)
        with override_settings(SECURITY_ENCRYPTION_KEYS=[second]):
            self.assertEqual(decrypt_secret(rotated), "test-sensitive-value")
            with self.assertRaises(ValidationError):
                decrypt_secret(encrypted)

    def test_strict_json_rejects_duplicates_arrays_nonfinite_and_controls(self):
        for payload in (b'{"amount":1,"amount":2}', b'[]', b'{"value":NaN}', b'{"value":1e999}', b'{"value":"\\u0000"}'):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                strict_json(payload)
        with self.assertRaises(ValidationError):
            strict_json(b'{"privilege":true}', allowed_fields={"name"})
        self.assertEqual(strict_json(b'{"name":"Alice"}', allowed_fields={"name"}), {"name": "Alice"})

    def test_new_passwords_require_twelve_characters(self):
        with self.assertRaises(ValidationError):
            validate_password("A7!short")

    def test_log_formatter_never_serializes_raw_messages_or_payloads(self):
        record = logging.LogRecord("test", logging.ERROR, "", 0, "password=SECRET API_KEY=PRIVATE", (), None)
        record.security_data = {"code": "login_failed", "password": "DO-NOT-LOG", "request_id": "request-123"}
        result = SafeJSONFormatter().format(record)
        self.assertNotIn("SECRET", result)
        self.assertNotIn("DO-NOT-LOG", result)
        self.assertNotIn("PRIVATE", result)
        self.assertEqual(json.loads(result)["code"], "login_failed")
