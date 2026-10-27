"""Odoo JSON-2 (19/20), Flutterwave v3 and pawaPay v2 adapters."""
import json
import os
import re
from decimal import Decimal
from urllib.parse import urlsplit
from django.conf import settings
from .http import request_json, token, IntegrationError


def mapped(name, key):
    try:
        value = json.loads(os.environ.get(name, "{}"))[str(key)]
        if isinstance(value, bool) or int(value) <= 0:
            raise ValueError
        return int(value)
    except (ValueError, KeyError, TypeError):
        raise IntegrationError("odoo_mapping_missing") from None


class OdooAdapter:
    def __init__(self, connection):
        self.connection = connection

    def call(self, model, method, values):
        if self.connection.base_url.rstrip("/") != settings.ODOO_BASE_URL.rstrip("/"):
            raise IntegrationError("odoo_endpoint_not_configured")
        database = os.environ.get("ODOO_DATABASE", "")
        if not database or "\r" in database or "\n" in database:
            raise IntegrationError("odoo_database_not_configured")
        return request_json(self.connection.base_url.rstrip("/") + f"/json/2/{model}/{method}", payload=values,
            headers={"Authorization": "bearer " + token("ODOO_API_KEY"), "X-Odoo-Database": database})

    def sync(self, operation, data):
        model, reference_field = ("account.move", "ref") if operation in {"invoice", "invoice_void"} else ("purchase.order", "partner_ref")
        reference = "NASIL:" + data["reference"]
        currency_id = mapped("ODOO_CURRENCY_ID_MAP", data["currency"])
        existing = self.call(model, "search_read", {"domain": [[reference_field, "=", reference]], "fields": ["id", "amount_total", "currency_id", "state"], "limit": 2})
        if not isinstance(existing, list) or len(existing) > 1:
            raise IntegrationError("odoo_reference_conflict")
        if operation in {"invoice_void", "purchase_void"}:
            if not existing:
                return "not_exported"
            remote = existing[0]
            if remote.get("state") == "cancel":
                return str(remote["id"])
            if remote.get("state") not in {"draft", "sent"}:
                raise IntegrationError("odoo_posted_document_requires_accountant")
            self.call(model, "button_cancel", {"ids": [remote["id"]]})
            confirmed = self.call(model, "read", {"ids": [remote["id"]], "fields": ["state"]})
            if not confirmed or confirmed[0].get("state") != "cancel":
                raise IntegrationError("odoo_cancellation_unconfirmed")
            return str(remote["id"])
        if existing:
            result = existing[0]
        else:
            if operation == "invoice":
                rate = Decimal(data["pricing"]["tax_rate"])
                taxes = [] if not rate else [mapped("ODOO_TAX_ID_MAP", f"{data['currency']}:{rate:.2f}")]
                values = {"move_type": "out_invoice", "partner_id": mapped("ODOO_CUSTOMER_ID_MAP", data["customer_id"]), "currency_id": currency_id,
                    "journal_id": mapped("ODOO_SALES_JOURNAL_ID_MAP", data["currency"]), "invoice_date": data["issued_date"], "invoice_date_due": data["due_date"], "ref": reference,
                    "invoice_line_ids": [[0, 0, {"name": data["number"], "quantity": 1, "price_unit": float(Decimal(data["pricing"]["subtotal"])),
                        "account_id": mapped("ODOO_INCOME_ACCOUNT_ID_MAP", data["currency"]), "tax_ids": [[6, 0, taxes]]}]]}
            else:
                values = {"partner_id": mapped("ODOO_SUPPLIER_ID_MAP", data["supplier_id"]), "currency_id": currency_id, "partner_ref": reference,
                    "order_line": [[0, 0, {"name": line["sku"], "product_id": mapped("ODOO_PRODUCT_ID_MAP", line["product_id"]),
                        "product_uom": mapped("ODOO_UOM_ID_MAP", line["unit"]), "product_qty": float(Decimal(line["quantity"])), "price_unit": float(Decimal(line["unit_price"])),
                        "taxes_id": [[6, 0, []]], "date_planned": data["planned_at"]}] for line in data["lines"]]}
            result_ids = self.call(model, "create", {"vals_list": [values]})
            if not isinstance(result_ids, list) or len(result_ids) != 1:
                raise IntegrationError("odoo_create_response_invalid")
            results = self.call(model, "read", {"ids": result_ids, "fields": ["id", "amount_total", "currency_id"]})
            if not results:
                raise IntegrationError("odoo_readback_failed")
            result = results[0]
        if Decimal(str(result["amount_total"])) != Decimal(data["amount"]) or result["currency_id"][0] != currency_id:
            raise IntegrationError("odoo_amount_or_currency_mismatch")
        # Accounting entries remain draft; the accountant controls posting in Odoo.
        return str(result["id"])


class FlutterwaveAdapter:
    base = "https://api.flutterwave.com/v3"
    def call(self, path, payload=None, method="POST"):
        return request_json(self.base + path, method=method, payload=payload, headers={"Authorization": "Bearer " + token("FLUTTERWAVE_SECRET_KEY")})

    def initiate(self, intent):
        customer = intent.invoice.quote.customer
        response = self.call("/payments", {"tx_ref": str(intent.reference), "amount": str(intent.amount), "currency": intent.currency,
            "redirect_url": settings.PUBLIC_SITE_URL + f"/portal/invoices/{intent.invoice_id}/", "customer": {"email": customer.email, "name": customer.full_name},
            "customizations": {"title": "NASIL Supply & Logistics"}})
        url = response.get("data", {}).get("link", "")
        parsed = urlsplit(url)
        if response.get("status") != "success" or parsed.scheme != "https" or parsed.hostname != "checkout.flutterwave.com" or parsed.username or parsed.password:
            raise IntegrationError("flutterwave_invalid_checkout")
        return url

    def verify(self, intent):
        path = f"/transactions/{intent.provider_transaction}/verify" if re.fullmatch(r"[0-9]{1,30}", intent.provider_transaction) else f"/transactions/verify_by_reference?tx_ref={intent.reference}"
        try:
            response = self.call(path, method="GET")
        except IntegrationError as error:
            if error.code in {"provider_http_400", "provider_http_404"}:
                raise IntegrationError("flutterwave_transaction_pending", retryable=True) from None
            raise
        data = response.get("data", {})
        if response.get("status") != "success" or data.get("status") != "successful":
            raise IntegrationError("flutterwave_payment_pending", retryable=True)
        if not re.fullmatch(r"[0-9]{1,30}", str(data.get("id"))) or (intent.provider_transaction and str(data.get("id")) != intent.provider_transaction) or data.get("tx_ref") != str(intent.reference) or data.get("currency") != intent.currency or Decimal(str(data.get("amount"))) != intent.amount:
            raise IntegrationError("flutterwave_payment_mismatch")
        return str(data["id"])


class PawaPayAdapter:
    def call(self, path, payload=None, method="POST"):
        return request_json(settings.PAWAPAY_BASE_URL.rstrip("/") + "/v2" + path, method=method, payload=payload, headers={"Authorization": "Bearer " + token("PAWAPAY_API_TOKEN")})

    def initiate(self, intent):
        response = self.call("/deposits", {"depositId": str(intent.reference), "payer": {"type": "MMO", "accountDetails": {"phoneNumber": intent.phone.lstrip("+"), "provider": intent.mobile_provider}},
            "amount": str(intent.amount), "currency": intent.currency, "clientReferenceId": str(intent.reference), "customerMessage": "NASIL invoice payment"})
        if response.get("status") not in {"ACCEPTED", "DUPLICATE_IGNORED"}:
            raise IntegrationError("pawapay_deposit_not_accepted")
        return ""

    def verify(self, intent):
        response = self.call(f"/deposits/{intent.reference}", method="GET")
        data = response.get("data", {})
        if response.get("status") != "FOUND" or data.get("status") not in {"COMPLETED", "FAILED"}:
            raise IntegrationError("pawapay_payment_pending", retryable=True)
        if data.get("status") == "FAILED":
            raise IntegrationError("pawapay_payment_failed")
        if data.get("depositId") != str(intent.reference) or data.get("clientReferenceId") != str(intent.reference) or data.get("currency") != intent.currency or Decimal(str(data.get("amount"))) != intent.amount:
            raise IntegrationError("pawapay_payment_mismatch")
        return str(intent.reference)
