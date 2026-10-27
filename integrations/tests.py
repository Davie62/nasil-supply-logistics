import json
import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone
from operations.test_commercial import CommercialFixtures
from operations.commercial import persist
from finance.models import Payment
from integrations.models import Connection, IntegrationJob, GatewayIntent
from integrations.services import create_intent, settle_intent, enqueue, invoice_snapshot, save_connection, retry_job
from integrations.tasks import run_job
from integrations.adapters import OdooAdapter, FlutterwaveAdapter, PawaPayAdapter
from integrations.http import safe_url, IntegrationError


class AdapterTests(CommercialFixtures, TestCase):
    pass


def connection(test, code="flutterwave"):
    return persist(Connection(name=code.title(), code=code, kind="accounting" if code == "odoo" else "payment_gateway",
        base_url={"odoo":"https://odoo.example.com", "flutterwave":"https://api.flutterwave.com", "pawapay":"https://api.sandbox.pawapay.io"}[code],
        credential_env={"odoo":"ODOO_API_KEY", "flutterwave":"FLUTTERWAVE_SECRET_KEY", "pawapay":"PAWAPAY_API_TOKEN"}[code], is_active=True), test.admin, "connection_test")


@override_settings(INTEGRATIONS_DELIVERY_ENABLED=True, PUBLIC_SITE_URL="https://nasil.example.com")
class GatewayTests(AdapterTests):
    def test_gateway_must_verify_amount_currency_and_reference(self):
        conn = connection(self)
        invoice = self.invoice()
        intent = create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave")
        data = {"status":"success", "data":{"status":"successful", "id":123, "amount":100, "currency":"UGX", "tx_ref":str(intent.reference)}}
        with patch.dict(os.environ, {"FLUTTERWAVE_SECRET_KEY":"test-secret"}), patch("integrations.adapters.request_json", return_value=data):
            self.assertEqual(FlutterwaveAdapter().verify(intent), "123")
            data["data"]["amount"] = 999
            with self.assertRaises(IntegrationError):
                FlutterwaveAdapter().verify(intent)
            data["data"].update(amount=100, currency="USD")
            with self.assertRaises(IntegrationError):
                FlutterwaveAdapter().verify(intent)
            data["data"].update(currency="UGX", tx_ref="another-invoice")
            with self.assertRaises(IntegrationError):
                FlutterwaveAdapter().verify(intent)
        self.assertFalse(Payment.objects.exists())

    def test_gateway_confirmation_posts_once_and_retries_same_intent(self):
        connection(self)
        invoice = self.invoice()
        intent = create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave")
        self.assertEqual(create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave").pk, intent.pk)
        with override_settings(INTEGRATIONS_SERVICE_USER_ID=self.admin.pk):
            first = settle_intent(intent.pk, "FLW-verified-123")
            self.assertEqual(settle_intent(intent.pk, "FLW-verified-123"), first)
        self.assertEqual(Payment.objects.count(), 1)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "succeeded")

    def test_payment_verified_after_manual_payment_is_retained_for_review(self):
        connection(self)
        invoice = self.invoice()
        intent = create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave")
        self.payment(invoice, amount=40)
        with override_settings(INTEGRATIONS_SERVICE_USER_ID=self.admin.pk):
            self.assertEqual(settle_intent(intent.pk, "FLW-late-receipt"), "review")
        intent.refresh_from_db()
        self.assertEqual(intent.provider_transaction, "FLW-late-receipt")
        self.assertEqual(intent.status, "review")
        self.assertEqual(Payment.objects.count(), 1)
        with self.assertRaises(ValidationError):
            create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave")

    @override_settings(PAWAPAY_CURRENCIES=["UGX"], PAWAPAY_PROVIDERS=["MTN_MOMO_UGA"])
    def test_pawapay_deposit_contract_and_server_status_verification(self):
        connection(self, "pawapay")
        invoice = self.invoice()
        intent = create_intent(actor=self.admin, invoice_id=invoice.pk, provider="pawapay", phone="+256700000001", mobile_provider="MTN_MOMO_UGA")
        with patch.dict(os.environ, {"PAWAPAY_API_TOKEN":"test-token"}), patch("integrations.adapters.request_json", return_value={"status":"ACCEPTED"}) as http:
            self.assertEqual(PawaPayAdapter().initiate(intent), "")
            payload = http.call_args.kwargs["payload"]
            self.assertEqual(payload["depositId"], str(intent.reference))
            self.assertEqual(payload["payer"]["accountDetails"]["phoneNumber"], "256700000001")
        response = {"status":"FOUND", "data":{"status":"COMPLETED", "depositId":str(intent.reference), "clientReferenceId":str(intent.reference), "amount":"100.00", "currency":"UGX"}}
        with patch.dict(os.environ, {"PAWAPAY_API_TOKEN":"test-token"}), patch("integrations.adapters.request_json", return_value=response):
            self.assertEqual(PawaPayAdapter().verify(intent), str(intent.reference))

    def test_flutterwave_webhook_cannot_post_client_supplied_money(self):
        connection(self)
        invoice = self.invoice()
        intent = create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave")
        intent.status = "pending"
        persist(intent, self.admin, "provider_accepted_test")
        body = {"event":"charge.completed", "data":{"tx_ref":str(intent.reference), "amount":9999999, "currency":"USD", "id":99}}
        with patch.dict(os.environ, {"FLUTTERWAVE_WEBHOOK_SECRET":"test-webhook-secret"}):
            self.assertEqual(self.client.post(reverse("integrations:flutterwave_webhook"), json.dumps(body), content_type="application/json").status_code, 403)
            self.assertEqual(self.client.post(reverse("integrations:flutterwave_webhook"), json.dumps(body), content_type="application/json", HTTP_VERIF_HASH="test-webhook-secret").status_code, 200)
        self.assertFalse(Payment.objects.exists())
        job = IntegrationJob.objects.get(operation="gateway_verify")
        self.assertEqual(job.payload, {"intent_id":intent.pk})

    def test_disabled_gateways_never_initiate_network_requests(self):
        connection(self)
        invoice = self.invoice()
        with override_settings(INTEGRATIONS_DELIVERY_ENABLED=False), patch("integrations.adapters.request_json") as http:
            with self.assertRaises(ValidationError):
                create_intent(actor=self.admin, invoice_id=invoice.pk, provider="flutterwave")
            self.assertEqual(run_job(99999), "disabled")
            http.assert_not_called()


class OdooAndTransportTests(AdapterTests):
    @override_settings(ODOO_BASE_URL="https://odoo.example.com")
    def test_odoo_invoice_exports_draft_with_explicit_mappings_and_total_readback(self):
        conn = connection(self, "odoo")
        invoice = self.invoice()
        response = {"id":42, "amount_total":100, "currency_id":[2,"UGX"]}
        environment = {"ODOO_API_KEY":"odoo-test", "ODOO_DATABASE":"nasil-test", "ODOO_CUSTOMER_ID_MAP":json.dumps({str(self.customer.pk):5}),
            "ODOO_CURRENCY_ID_MAP":'{"UGX":2}', "ODOO_SALES_JOURNAL_ID_MAP":'{"UGX":3}', "ODOO_INCOME_ACCOUNT_ID_MAP":'{"UGX":4}'}
        with patch.dict(os.environ, environment), patch("integrations.adapters.request_json", side_effect=[[],[42],[response]]) as http:
            self.assertEqual(OdooAdapter(conn).sync("invoice", invoice_snapshot(invoice)), "42")
            create = http.call_args_list[1].kwargs["payload"]["vals_list"][0]
            self.assertEqual(create["move_type"], "out_invoice")
            self.assertEqual(create["ref"], "NASIL:"+str(invoice.reference))
            self.assertNotIn("action_post", str(http.call_args_list))
        with patch.dict(os.environ, environment), patch("integrations.adapters.request_json", return_value=[response]) as http:
            self.assertEqual(OdooAdapter(conn).sync("invoice", invoice_snapshot(invoice)), "42")
            self.assertEqual(http.call_count, 1)

    def test_transport_rejects_private_endpoints_and_unapproved_hosts(self):
        with override_settings(INTEGRATIONS_ALLOWED_HOSTS=["odoo.example.com"]), patch("integrations.http.socket.getaddrinfo", return_value=[(None,None,None,None,("127.0.0.1",443))]):
            with self.assertRaises(IntegrationError):
                safe_url("https://odoo.example.com/json/2/account.move/create")
        for url in ("http://api.flutterwave.com/v3", "https://user:secret@api.flutterwave.com/v3", "https://attacker.example/v3"):
            with self.assertRaises(IntegrationError):
                safe_url(url)

    @override_settings(INTEGRATIONS_DELIVERY_ENABLED=True)
    def test_outbox_retries_redacted_errors_and_admin_can_requeue_failures(self):
        conn = connection(self, "odoo")
        invoice = self.invoice()
        job = enqueue(actor=self.admin, connection=conn, operation="invoice", event_key="retry-test", payload=invoice_snapshot(invoice))
        with patch("integrations.tasks.OdooAdapter.sync", side_effect=IntegrationError("provider_http_503", retryable=True)):
            self.assertEqual(run_job(job.pk), "retry")
        job.refresh_from_db()
        self.assertEqual(job.error_code, "provider_http_503")
        job.next_attempt_at = timezone.now()-timedelta(seconds=1)
        persist(job, self.admin, "test_due")
        with patch("integrations.tasks.OdooAdapter.sync", side_effect=IntegrationError("credentials_not_configured")):
            self.assertEqual(run_job(job.pk), "failed")
        job.refresh_from_db()
        retry_job(actor=self.admin, record_id=job.pk, expected_version=job.version)
        job.refresh_from_db()
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.attempts, 0)
