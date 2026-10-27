from datetime import timedelta
from io import BytesIO
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader

from accounts.models import User
from core.models import AuditRecord
from core.test_helpers import booked_shipment
from customers.models import Customer
from operations.services import record_delivery_proof
from payments.services import issue_invoice, void_invoice
from quotations.workflows import transition_quote, update_quote
from .models import CustomerAccess, CustomerNotification, DeliveryAttempt, NotificationPreference, PortalInvitation, RateBucket
from .notifications import enqueue_event, recipient_for, render_delivery
from .services import activate_customer, invite_customer, invitation_token, save_preferences, set_access
from .tasks import deliver_notification, dispatch_due, MAX_ATTEMPTS
from . import providers


class CustomerServicesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="portal-admin", email="portal-admin@example.com", is_staff=True, is_superuser=True)
        self.customer = Customer.objects.create(full_name="PRIVATE CUSTOMER A", email="customer-a@example.com", phone="+256700000001", address="PRIVATE ADDRESS A")
        self.other = Customer.objects.create(full_name="PRIVATE CUSTOMER B", email="customer-b@example.com", phone="+256700000002")
        self.invitation = invite_customer(actor=self.admin, customer_id=self.customer.pk)
        self.access = activate_customer(token=invitation_token(self.invitation), username="customer-a", password="Strong-customer-password-2026!")
        self.user = self.access.user
        invitation = invite_customer(actor=self.admin, customer_id=self.other.pk)
        self.other_user = activate_customer(token=invitation_token(invitation), username="customer-b", password="Strong-customer-password-2026!").user
        self.client.force_login(self.user)

    def preferences(self, **extra):
        return save_preferences(actor=self.user, data={"preferred_channel": "email", "sms_number": "", "sms_consent": False, "enabled": True,
            "quotation_updates": True, "shipment_updates": True, "delivery_updates": True, **extra})

    def proof(self, customer=None):
        shipment = booked_shipment(customer or self.customer, status="delivered")
        buffer = BytesIO()
        Image.new("RGB", (100, 40), "white").save(buffer, format="PNG")
        return record_delivery_proof(actor=self.admin, shipment_id=shipment.pk, recipient_name="PRIVATE RECIPIENT", delivered_at=timezone.now(), notes="PRIVATE DELIVERY NOTES", evidence=SimpleUploadedFile("signed.png", buffer.getvalue(), content_type="image/png"))

    def notification(self):
        shipment = booked_shipment(self.customer)
        return CustomerNotification.objects.get(audit__shipment=shipment, kind="shipment_update")

    def test_activation_is_verified_customer_only_without_staff_roles(self):
        self.assertTrue(self.user.is_verified)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.user.groups.count(), 0)
        self.assertEqual(self.access.customer_id, self.customer.pk)
        self.assertFalse(hasattr(self.user, "profile"))

    def test_activation_expired_replayed_tampered_and_revoked_tokens_fail(self):
        with self.assertRaises(ValidationError):
            activate_customer(token=invitation_token(self.invitation), username="replay", password="Strong-customer-password-2026!")
        third = Customer.objects.create(full_name="Third", email="third@example.com", phone="0")
        invitation = invite_customer(actor=self.admin, customer_id=third.pk)
        for token in ("tampered", invitation_token(invitation) + "x"):
            self.client.logout()
            self.assertEqual(self.client.get(reverse("portal_activate", args=[token])).status_code, 404)
        PortalInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(reverse("portal_activate", args=[invitation_token(invitation)])).status_code, 404)

    def test_reinviting_revokes_previous_link_and_email_changes_invalidate_it(self):
        customer = Customer.objects.create(full_name="Third", email="third@example.com", phone="0")
        first = invite_customer(actor=self.admin, customer_id=customer.pk)
        second = invite_customer(actor=self.admin, customer_id=customer.pk)
        from .services import resolve_invitation
        with self.assertRaises(ValidationError):
            resolve_invitation(invitation_token(first))
        customer.email = "different@example.com"
        customer.save()
        with self.assertRaises(ValidationError):
            resolve_invitation(invitation_token(second))

    def test_existing_email_is_never_claimed_by_invitation(self):
        customer = Customer.objects.create(full_name="Staff email", email=self.admin.email, phone="0")
        with self.assertRaises(ValidationError):
            invite_customer(actor=self.admin, customer_id=customer.pk)

    def test_login_customer_and_staff_boundaries_and_safe_redirect(self):
        self.client.logout()
        response = self.client.post(reverse("portal_login") + "?next=https://attacker.example/", {"username": self.user.username, "password": "Strong-customer-password-2026!"})
        self.assertRedirects(response, reverse("portal_dashboard"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("portal_dashboard")).status_code, 403)

    def test_portal_login_lockout_and_post_logout(self):
        self.assertEqual(self.client.get(reverse("portal_logout")).status_code, 405)
        self.client.logout()
        for _ in range(5):
            self.client.post(reverse("portal_login"), {"username": self.user.username, "password": "incorrect"})
        response = self.client.post(reverse("portal_login"), {"username": self.user.username, "password": "Strong-customer-password-2026!"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_portal_remember_me_is_optional_and_matches_session_expiry(self):
        self.client.logout()
        credentials = {"username": self.user.username, "password": "Strong-customer-password-2026!"}
        response = self.client.post(reverse("portal_login"), {**credentials, "remember_me": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 30 * 24 * 60 * 60)
        self.client.logout()
        response = self.client.post(reverse("portal_login"), credentials)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_portal_dashboard_and_lists_are_scoped_to_owner(self):
        own = booked_shipment(self.customer)
        other = booked_shipment(self.other)
        for name in ("portal_dashboard", "portal_quotes", "portal_shipments"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, other.tracking_number)
            self.assertNotContains(response, self.other.full_name)
        self.assertContains(self.client.get(reverse("portal_shipments")), own.tracking_number)
        self.assertEqual(self.client.get(reverse("portal_shipment", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("portal_quote", args=[other.quote_id])).status_code, 404)

    def test_owned_invoice_and_proof_downloads_reject_other_customers(self):
        proof = self.proof()
        other = self.proof(self.other)
        invoice = issue_invoice(actor=self.admin, quote_id=proof.shipment.quote_id, due_date=timezone.localdate())
        other_invoice = issue_invoice(actor=self.admin, quote_id=other.shipment.quote_id, due_date=timezone.localdate())
        self.assertContains(self.client.get(reverse("portal_invoice", args=[invoice.pk])), invoice.number)
        for name, pk in (("portal_invoice", other_invoice.pk), ("portal_invoice_pdf", other_invoice.pk), ("portal_evidence", other.pk)):
            self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 404)
        response = self.client.get(reverse("portal_evidence", args=[proof.pk]))
        self.assertEqual(b"".join(response.streaming_content), bytes(proof.evidence))
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_public_tracking_redacts_pii_audit_notes_and_signature(self):
        proof = self.proof()
        shipment = proof.shipment
        self.client.logout()
        response = self.client.get(reverse("public_tracking_result", args=[shipment.tracking_number]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivered")
        self.assertContains(response, "Delivery proof has been recorded")
        for secret in (self.customer.full_name, self.customer.email, self.customer.address, "PRIVATE RECIPIENT", "PRIVATE DELIVERY NOTES", "fixture-preparer", "PRIVATE CARGO", "Kampala", "Jinja", str(proof.reference), "Download signed"):
            self.assertNotContains(response, secret)
        self.assertNotIn("shipment", response.context)
        self.assertNotIn("changes", str(response.context["tracking"]))
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(self.client.get(reverse("portal_evidence", args=[proof.pk])).status_code, 302)

    def test_public_tracking_form_supports_ids_and_limits_enumeration(self):
        shipment = booked_shipment(self.customer)
        self.assertEqual(len(shipment.tracking_number), 36)
        self.client.logout()
        self.assertRedirects(self.client.post(reverse("public_tracking"), {"tracking_number": shipment.tracking_number.lower()}), reverse("public_tracking_result", args=[shipment.tracking_number]))
        self.assertEqual(self.client.post(reverse("public_tracking"), {"tracking_number": "bad"}).status_code, 400)
        self.assertEqual(self.client.get(reverse("public_tracking_result", args=["TRK-NOTFOUND"])).status_code, 404)
        RateBucket.objects.all().delete()
        for _ in range(60):
            self.assertEqual(self.client.get(reverse("public_tracking")).status_code, 200)
        self.assertEqual(self.client.get(reverse("public_tracking")).status_code, 429)

    def test_access_revocation_applies_to_existing_session_and_delivery(self):
        notification = self.notification()
        set_access(actor=self.admin, customer_id=self.customer.pk, enabled=False)
        self.assertEqual(self.client.get(reverse("portal_dashboard")).status_code, 403)
        with override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True), patch("customer_services.providers.sendgrid") as provider:
            self.assertEqual(deliver_notification.run(notification.pk), "suppressed")
            provider.assert_not_called()

    def test_notifications_are_deduplicated_and_private_auth_messages_hidden(self):
        notification = self.notification()
        enqueue_event(notification.audit)
        self.assertEqual(CustomerNotification.objects.filter(event_key=notification.event_key).count(), 1)
        response = self.client.get(reverse("portal_notifications"))
        self.assertNotContains(response, "Activate your secure")
        self.assertNotContains(response, "invitation")
        self.assertEqual(self.client.get(reverse("portal_notification_read", args=[notification.pk])).status_code, 405)
        other = CustomerNotification.objects.filter(customer=self.other).first()
        self.assertEqual(self.client.post(reverse("portal_notification_read", args=[other.pk])).status_code, 404)
        self.client.post(reverse("portal_notification_read", args=[notification.pk]))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_preferences_require_sms_consent_and_apply_before_delivery(self):
        with self.assertRaises(ValidationError):
            self.preferences(preferred_channel="sms", sms_number="0700000000", sms_consent=True)
        with self.assertRaises(ValidationError):
            self.preferences(preferred_channel="sms", sms_number="+256700000001", sms_consent=False)
        self.preferences(preferred_channel="sms", sms_number="+256700000001", sms_consent=True)
        notification = self.notification()
        self.assertEqual(notification.channel, "sms")
        self.preferences(enabled=False)
        with override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True), patch("customer_services.providers.twilio") as provider:
            self.assertEqual(deliver_notification.run(notification.pk), "suppressed")
            provider.assert_not_called()

    def test_changed_email_is_not_silently_verified(self):
        self.customer.email = "new@example.com"
        self.customer.save()
        self.assertEqual(recipient_for(self.customer, "shipment_update")[2], "email_changed_requires_verification")

    def test_quotation_shipment_and_delivery_signals_enqueue_correct_events(self):
        proof = self.proof()
        kinds = set(CustomerNotification.objects.filter(customer=self.customer).values_list("kind", flat=True))
        self.assertTrue({"quote_approved", "shipment_update", "delivery_confirmed", "proof_available"}.issubset(kinds))
        notification = CustomerNotification.objects.get(audit__shipment=proof.shipment, kind="delivery_confirmed")
        self.assertEqual(notification.channel, "email")
        self.assertEqual(notification.recipient, self.access.verified_email)

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=False)
    def test_delivery_disabled_never_calls_provider_or_broker(self):
        with patch("customer_services.tasks.deliver_notification.delay") as broker, patch("customer_services.providers.sendgrid") as provider:
            notification = self.notification()
            self.assertEqual(deliver_notification.run(notification.pk), "disabled")
            self.assertEqual(dispatch_due(), 0)
            broker.assert_not_called()
            provider.assert_not_called()

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True)
    def test_email_delivery_marks_provider_acceptance_and_is_not_repeated(self):
        notification = self.notification()
        with patch("customer_services.providers.sendgrid", return_value="sg-message") as provider:
            self.assertEqual(deliver_notification.run(notification.pk), "sent")
            self.assertEqual(deliver_notification.run(notification.pk), "not_due")
            self.assertEqual(provider.call_count, 1)
        notification.refresh_from_db()
        self.assertEqual(notification.provider, "sendgrid")
        self.assertEqual(notification.status, "sent")

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True)
    def test_sms_primary_failure_uses_africas_talking_fallback(self):
        self.preferences(preferred_channel="sms", sms_number="+256700000001", sms_consent=True)
        notification = self.notification()
        with patch("customer_services.providers.twilio", side_effect=providers.ProviderError("http_503")), patch("customer_services.providers.africastalking", return_value="at-message"):
            self.assertEqual(deliver_notification.run(notification.pk), "sent")
        notification.refresh_from_db()
        self.assertEqual(notification.provider, "africastalking")
        self.assertEqual(notification.delivery_attempts.count(), 2)

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True)
    def test_invalid_sms_recipient_does_not_failover(self):
        self.preferences(preferred_channel="sms", sms_number="+256700000001", sms_consent=True)
        notification = self.notification()
        with patch("customer_services.providers.twilio", side_effect=providers.ProviderError("http_400", retryable=False, fallback=False)), patch("customer_services.providers.africastalking") as fallback:
            self.assertEqual(deliver_notification.run(notification.pk), "exhausted")
            fallback.assert_not_called()

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True)
    def test_temporary_failure_persists_retry_even_when_fallback_unconfigured(self):
        self.preferences(preferred_channel="sms", sms_number="+256700000001", sms_consent=True)
        notification = self.notification()
        with patch("customer_services.providers.twilio", side_effect=providers.ProviderError("http_503")), patch("customer_services.providers.africastalking", side_effect=providers.ProviderError("not_configured", retryable=False)), patch.object(deliver_notification, "retry", side_effect=RuntimeError("retry")):
            with self.assertRaises(RuntimeError):
                deliver_notification.run(notification.pk)
        notification.refresh_from_db()
        self.assertEqual(notification.status, "failed")
        self.assertGreater(notification.next_attempt_at, timezone.now())

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True)
    def test_retry_is_bounded(self):
        notification = self.notification()
        CustomerNotification.objects.filter(pk=notification.pk).update(attempts=MAX_ATTEMPTS - 1)
        with patch("customer_services.providers.sendgrid", side_effect=providers.ProviderError("http_503")):
            self.assertEqual(deliver_notification.run(notification.pk), "exhausted")

    def test_password_recovery_is_queued_for_customers_only_and_hides_tokens(self):
        self.client.logout()
        self.preferences(enabled=False)
        response = self.client.post(reverse("portal_password_reset"), {"email": self.customer.email})
        self.assertRedirects(response, reverse("portal_reset_sent"))
        notification = CustomerNotification.objects.get(customer=self.customer, kind="password_reset")
        self.assertEqual(recipient_for(self.customer, "password_reset")[2], "")
        text, html, sms = render_delivery(notification)
        self.assertIn("/portal/reset/", text)
        self.assertEqual(self.client.post(reverse("portal_password_reset"), {"email": self.admin.email}).status_code, 302)
        self.assertEqual(CustomerNotification.objects.filter(kind="password_reset").count(), 1)
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("portal_notifications")), notification.payload["token"])

    def test_invoice_snapshot_lock_and_portal_pdf(self):
        shipment = booked_shipment(self.customer)
        invoice = issue_invoice(actor=self.admin, quote_id=shipment.quote_id, due_date=timezone.localdate())
        response = self.client.get(reverse("portal_invoice_pdf", args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        text = "".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
        self.assertIn(invoice.number, text)
        self.assertIn("Export audit reference", text)
        with self.assertRaises(ValidationError):
            update_quote(quote_id=shipment.quote_id, actor=self.admin, data={"customer": self.other})
        void_invoice(actor=self.admin, invoice_id=invoice.pk, reason="Duplicate billing request")
        self.assertContains(self.client.get(reverse("portal_invoice", args=[invoice.pk])), "Void")

    def test_csrf_protection_on_preferences_and_invites(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("portal_preferences"), {}).status_code, 403)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("customer_portal_access", args=[self.customer.pk]), {"action": "disable"}).status_code, 403)

    def test_staff_can_view_access_screen_but_customer_cannot(self):
        url = reverse("customer_portal_access", args=[self.customer.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), self.user.username)

    @override_settings(SENDGRID_API_KEY="test-key", DEFAULT_FROM_EMAIL="nasil@example.com")
    def test_sendgrid_adapter_uses_expected_contract_without_real_network(self):
        notification = self.notification()
        with patch("customer_services.providers.request_provider", return_value=(202, {"X-Message-Id": "id-123"}, {})) as http:
            self.assertEqual(providers.sendgrid(notification, "Text", "<p>HTML</p>"), "id-123")
            self.assertEqual(http.call_args.args[0], "https://api.sendgrid.com/v3/mail/send")
            import json
            self.assertEqual(json.loads(http.call_args.args[1])["personalizations"][0]["to"][0]["email"], self.customer.email)

    @override_settings(AFRICASTALKING_USERNAME="sandbox", AFRICASTALKING_API_KEY="test-key", AFRICASTALKING_SANDBOX=True)
    def test_africas_talking_adapter_checks_recipient_acceptance(self):
        notification = self.notification()
        with patch("customer_services.providers.request_provider", return_value=(201, {}, {"SMSMessageData": {"Recipients": [{"statusCode": 101, "messageId": "AT-123"}]}})) as http:
            self.assertEqual(providers.africastalking(notification, "SMS"), "AT-123")
            self.assertIn("api.sandbox.africastalking.com", http.call_args.args[0])

    def test_http_errors_are_redacted(self):
        error = HTTPError("https://provider.example", 401, "PRIVATE BODY", {}, None)
        with patch("customer_services.providers.urlopen", side_effect=error):
            with self.assertRaises(providers.ProviderError) as result:
                providers.request_provider("https://provider.example", b"", {})
        self.assertEqual(str(result.exception), "http_401")

    def test_activation_view_creates_customer_session(self):
        third = Customer.objects.create(full_name="Third", email="third@example.com", phone="0")
        invitation = invite_customer(actor=self.admin, customer_id=third.pk)
        self.client.logout()
        response = self.client.post(reverse("portal_activate", args=[invitation_token(invitation)]), {"username": "customer-third", "password1": "Strong-customer-password-2026!", "password2": "Strong-customer-password-2026!"})
        self.assertRedirects(response, reverse("portal_dashboard"))
        self.assertEqual(CustomerAccess.objects.get(customer=third).user.username, "customer-third")

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=False)
    def test_staff_can_find_create_and_open_invitation_without_silent_redirect(self):
        third = Customer.objects.create(full_name="Third", email="third@example.com", phone="0")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("customer_list"))
        self.assertContains(response, "Portal access")
        response = self.client.post(reverse("customer_portal_access", args=[third.pk]), {"action": "invite"}, follow=True)
        self.assertContains(response, "Email delivery is disabled locally")
        self.assertContains(response, 'id="activation-link"')
        invitation = PortalInvitation.objects.get(customer=third)
        path = reverse("portal_activate", args=[invitation_token(invitation)])
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "private or incognito window")
        response = self.client.post(path, {"username": "should-not-exist", "password1": "Strong-customer-password-2026!", "password2": "Strong-customer-password-2026!"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="should-not-exist").exists())
        self.client.logout()
        self.assertContains(self.client.get(path), "Activate your customer portal")

    def test_preference_form_is_owned_and_validates_sms(self):
        response = self.client.post(reverse("portal_preferences"), {"preferred_channel": "sms", "sms_number": "123", "enabled": "on", "sms_consent": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(reverse("portal_preferences"), {"preferred_channel": "sms", "sms_number": "+256700000001", "enabled": "on", "sms_consent": "on", "shipment_updates": "on", "quotation_updates": "on", "delivery_updates": "on"})
        self.assertRedirects(response, reverse("portal_preferences"))
        self.assertEqual(NotificationPreference.objects.get(customer=self.customer).preferred_channel, "sms")
        self.assertEqual(NotificationPreference.objects.get(customer=self.other).preferred_channel, "email")

    def test_customer_lists_use_server_search_and_pagination(self):
        from quotations.models import Quote
        for index in range(26):
            Quote.objects.create(customer=self.customer, pickup_location="Pickup", destination=f"Port {index}", cargo_description="Goods", weight=1)
        response = self.client.get(reverse("portal_quotes"), {"page": 2})
        self.assertEqual(len(response.context["records"]), 1)
        response = self.client.get(reverse("portal_quotes"), {"q": "Port 25"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    @override_settings(NOTIFICATIONS_DELIVERY_ENABLED=True)
    def test_broker_is_only_published_after_commit_and_failure_keeps_outbox(self):
        with patch("customer_services.tasks.deliver_notification.delay", side_effect=RuntimeError("Broker unavailable")) as broker:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                notification = self.notification()
            self.assertGreater(len(callbacks), 0)
            broker.assert_not_called()
            for callback in callbacks:
                callback()
            self.assertTrue(CustomerNotification.objects.filter(pk=notification.pk, status="queued").exists())

    def test_queue_failure_rolls_back_business_event_and_audit(self):
        from quotations.models import Quote
        from quotations.workflows import create_quote
        quote = create_quote(actor=self.admin, data={"customer": self.customer, "pickup_location": "A", "destination": "B", "cargo_description": "Goods", "weight": 1, "base_amount": 100, "valid_until": timezone.localdate()})
        with patch("customer_services.signals.enqueue_event", side_effect=RuntimeError("Outbox unavailable")):
            with self.assertRaises(RuntimeError):
                transition_quote(actor=self.admin, quote_id=quote.pk, target="reviewed")
        quote.refresh_from_db()
        self.assertEqual(quote.status, "pending")
        self.assertEqual(quote.audit_records.count(), 1)

    def test_invoiced_unbooked_quote_cannot_be_reopened_or_reassigned(self):
        from quotations.workflows import create_quote
        quote = create_quote(actor=self.admin, data={"customer": self.customer, "pickup_location": "A", "destination": "B", "cargo_description": "Goods", "weight": 1, "base_amount": 100, "valid_until": timezone.localdate()})
        transition_quote(actor=self.admin, quote_id=quote.pk, target="reviewed")
        approver = User.objects.create_user(username="finance-approver", email="finance@example.com", is_staff=True, is_superuser=True)
        quote = transition_quote(actor=approver, quote_id=quote.pk, target="approved")
        issue_invoice(actor=self.admin, quote_id=quote.pk, due_date=timezone.localdate())
        with self.assertRaises(ValidationError):
            transition_quote(actor=self.admin, quote_id=quote.pk, target="reviewed", reason="Change customer")

    @override_settings(TWILIO_ACCOUNT_SID="AC" + "a" * 32, TWILIO_AUTH_TOKEN="test-token", TWILIO_FROM_NUMBER="+15005550006")
    def test_twilio_adapter_uses_form_encoding_and_sender(self):
        notification = self.notification()
        notification.recipient = "+256700000001"
        with patch("customer_services.providers.request_provider", return_value=(201, {}, {"sid": "SM-test"})) as http:
            self.assertEqual(providers.twilio(notification, "SMS body"), "SM-test")
            from urllib.parse import parse_qs
            data = parse_qs(http.call_args.args[1].decode())
            self.assertEqual(data["To"], ["+256700000001"])

    def test_recovery_link_changes_password_once(self):
        self.client.logout()
        self.client.post(reverse("portal_password_reset"), {"email": self.customer.email})
        notification = CustomerNotification.objects.get(kind="password_reset", customer=self.customer)
        reset_url = reverse("portal_reset_confirm", args=[notification.payload["uid"], notification.payload["token"]])
        response = self.client.get(reset_url)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response.url, {"new_password1": "Replacement-customer-password-2026!", "new_password2": "Replacement-customer-password-2026!"})
        self.assertRedirects(response, reverse("portal_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Replacement-customer-password-2026!"))
        response = self.client.get(reset_url)
        self.assertContains(response, "invalid")
