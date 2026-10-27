import hashlib
import json
import re
from datetime import timedelta
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from accounts.models import User
from core.business_rules import require_permission, validate_version
from operations.services import require_admin
from operations.commercial import persist, editable_data
from payments.models import Invoice
from finance.services import balance_due, record_payment
from .models import Connection, IntegrationJob, GatewayIntent, WebhookEvent
from .http import IntegrationError

CREDENTIALS = {"odoo": "ODOO_API_KEY", "flutterwave": "FLUTTERWAVE_SECRET_KEY", "pawapay": "PAWAPAY_API_TOKEN"}


def schedule(job):
    if not settings.INTEGRATIONS_DELIVERY_ENABLED:
        return
    def publish():
        try:
            from .tasks import run_job
            run_job.delay(job.pk)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Integration publication deferred: %s", job.reference)
    transaction.on_commit(publish)


@transaction.atomic
def save_connection(*, actor, data, record_id=None, expected_version=None):
    require_permission(actor, "integrations.change_connection" if record_id else "integrations.add_connection")
    require_admin(actor)
    editable_data(data, ("name", "code", "kind", "base_url", "credential_env", "webhook_secret_env", "is_active"))
    connection = Connection.objects.select_for_update().get(pk=record_id) if record_id else Connection()
    validate_version(connection, expected_version)
    code = data["code"]
    if record_id and code != connection.code:
        raise ValidationError("Provider codes are fixed after connection creation.")
    if code not in CREDENTIALS or data["credential_env"] != CREDENTIALS[code]:
        raise ValidationError("Use provider codes odoo/flutterwave/pawapay and the matching documented credential environment variable.")
    expected = {"odoo": settings.ODOO_BASE_URL, "flutterwave": "https://api.flutterwave.com", "pawapay": settings.PAWAPAY_BASE_URL}[code]
    if data["base_url"].rstrip("/") != expected.rstrip("/"):
        raise ValidationError("Provider URL must exactly match the configured HTTPS origin.")
    parsed = urlsplit(data["base_url"])
    if parsed.scheme != "https" or parsed.hostname not in settings.INTEGRATIONS_ALLOWED_HOSTS or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValidationError("Choose an approved HTTPS provider origin without credentials or paths.")
    if data["kind"] != ("accounting" if code == "odoo" else "payment_gateway") or (data.get("webhook_secret_env") and data["webhook_secret_env"] != "FLUTTERWAVE_WEBHOOK_SECRET"):
        raise ValidationError("Provider type or webhook credential name does not match the configured adapter.")
    for key, value in data.items():
        setattr(connection, key, value)
    return persist(connection, actor, "connection_saved")


def enqueue(*, actor, connection, operation, event_key, payload):
    job = IntegrationJob.objects.filter(event_key=event_key).first()
    if job:
        if job.connection_id != connection.pk or job.payload != payload or job.operation != operation:
            raise ValidationError("Integration event key already has different data.")
        return job
    job = persist(IntegrationJob(connection=connection, operation=operation, event_key=event_key, payload=payload, requested_by=actor, next_attempt_at=timezone.now()), actor, "integration_queued")
    schedule(job)
    return job


def invoice_snapshot(invoice):
    return {"reference": str(invoice.reference), "number": invoice.number, "customer_id": invoice.quote.customer_id, "currency": invoice.currency,
        "amount": str(invoice.amount), "pricing": invoice.pricing, "issued_date": invoice.issued_at.date().isoformat(), "due_date": invoice.due_date.isoformat()}


def purchase_snapshot(purchase):
    return {"reference": str(purchase.reference), "number": purchase.number, "supplier_id": purchase.supplier_id, "currency": purchase.currency,
        "amount": str(purchase.total), "planned_at": timezone.now().strftime("%Y-%m-%d %H:%M:%S"), "lines": [{"product_id": line.stock.product_id,
            "sku": line.stock.product.sku, "unit": line.stock.product.unit, "quantity": str(line.quantity), "unit_price": str(line.unit_price)} for line in purchase.lines.select_related("stock__product")]}


@transaction.atomic
def queue_document(*, actor, record_id, document_type, document_id, expected_version=None):
    require_permission(actor, "integrations.add_integrationjob")
    connection = Connection.objects.filter(pk=record_id, code="odoo", is_active=True).first()
    if not connection:
        raise ValidationError("Document synchronization requires an active Odoo connection.")
    if document_type == "invoice":
        require_permission(actor, "payments.view_invoice")
        document = Invoice.objects.get(pk=document_id, status="issued")
        payload = invoice_snapshot(document)
    elif document_type == "purchase_order":
        require_permission(actor, "procurement.view_purchaseorder")
        from procurement.models import PurchaseOrder
        document = PurchaseOrder.objects.get(pk=document_id, status__in=["approved", "sent", "partially_received", "received"])
        payload = purchase_snapshot(document)
    else:
        raise ValidationError("Choose an invoice or approved purchase order.")
    key = f"odoo:{document_type}:{document.reference}"
    existing = IntegrationJob.objects.filter(event_key=key).first()
    return existing or enqueue(actor=actor, connection=connection, operation=document_type, event_key=key, payload=payload)


@transaction.atomic
def create_intent(*, actor, invoice_id, provider, phone="", mobile_provider=""):
    if not settings.INTEGRATIONS_DELIVERY_ENABLED:
        raise ValidationError("Online payments are not enabled yet. Contact NASIL for payment instructions.")
    invoice = Invoice.objects.select_for_update().select_related("quote__customer").get(pk=invoice_id)
    if actor.is_staff:
        require_permission(actor, "integrations.add_gatewayintent", "payments.view_invoice")
    else:
        from customer_services.models import CustomerAccess
        if not actor.is_active or not actor.is_verified or not CustomerAccess.objects.filter(user=actor, enabled=True, customer_id=invoice.quote.customer_id).exists():
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
    if invoice.status != "issued" or balance_due(invoice) <= 0 or provider not in {"flutterwave", "pawapay"}:
        raise ValidationError("Choose an unpaid issued invoice and a supported payment provider.")
    connection = Connection.objects.filter(code=provider, is_active=True).first()
    if not connection:
        raise ValidationError("This payment provider is not configured.")
    existing = GatewayIntent.objects.filter(invoice=invoice, status__in=["created", "pending", "review"]).first()
    if existing:
        if existing.status == "review":
            raise ValidationError("An earlier payment needs staff review before another payment can be started.")
        if existing.connection_id != connection.pk:
            raise ValidationError("An invoice payment is already in progress with another provider. Wait for its final status.")
        return existing
    if provider == "pawapay" and (invoice.currency not in settings.PAWAPAY_CURRENCIES or not re.fullmatch(r"\+[1-9]\d{7,14}", phone) or mobile_provider not in settings.PAWAPAY_PROVIDERS):
        raise ValidationError("pawaPay requires a supported currency, country-code phone number and configured mobile-money provider.")
    intent = persist(GatewayIntent(connection=connection, invoice=invoice, amount=balance_due(invoice), currency=invoice.currency,
        phone=phone, mobile_provider=mobile_provider, created_by=actor), actor, "payment_initiation_requested")
    enqueue(actor=actor, connection=connection, operation="gateway_init", event_key=f"gateway:init:{intent.reference}", payload={"intent_id": intent.pk})
    return intent


def queue_verification(intent):
    key = f"gateway:verify:{intent.reference}"
    return enqueue(actor=intent.created_by, connection=intent.connection, operation="gateway_verify", event_key=key, payload={"intent_id": intent.pk})


@transaction.atomic
def settle_intent(intent_id, provider_reference):
    original = GatewayIntent.objects.get(pk=intent_id)
    Invoice.objects.select_for_update().get(pk=original.invoice_id)
    intent = GatewayIntent.objects.select_for_update().select_related("connection", "invoice").get(pk=intent_id)
    if intent.payment_id:
        return str(intent.payment.reference)
    service_user = User.objects.filter(pk=settings.INTEGRATIONS_SERVICE_USER_ID).first()
    require_permission(service_user, "finance.add_payment")
    intent.provider_transaction = provider_reference
    try:
        with transaction.atomic():
            payment = record_payment(actor=service_user, invoice=intent.invoice, amount=intent.amount, currency=intent.currency, method="gateway",
                external_reference=provider_reference, idempotency_key=f"gateway:{intent.reference}", provider=intent.connection.code)
    except (ValidationError, IntegrityError):
        intent.status, intent.error_code = "review", "verified_payment_requires_allocation"
        persist(intent, service_user, "payment_requires_review")
        return "review"
    intent.payment, intent.status, intent.provider_transaction = payment, "succeeded", provider_reference
    persist(intent, service_user, "gateway_payment_verified")
    digest = hashlib.sha256(json.dumps({"reference": provider_reference, "amount": str(intent.amount), "currency": intent.currency}, sort_keys=True).encode()).hexdigest()
    persist(WebhookEvent(connection=intent.connection, event_id=provider_reference, payload_digest=digest, payment=payment), service_user, "provider_confirmation_recorded")
    return str(payment.reference)


@transaction.atomic
def retry_job(*, actor, record_id, expected_version=None):
    require_permission(actor, "integrations.change_integrationjob")
    require_admin(actor)
    job = IntegrationJob.objects.select_for_update().get(pk=record_id)
    validate_version(job, expected_version)
    if job.status != "failed":
        raise ValidationError("Only failed jobs can be retried; successful deliveries are retained.")
    if job.operation.startswith("gateway"):
        intent = GatewayIntent.objects.select_for_update().get(pk=job.payload["intent_id"])
        if intent.payment_id:
            raise ValidationError("This payment has already been posted.")
        if job.operation == "gateway_init" and job.error_code in {"provider_network_error", "invalid_provider_response"}:
            intent.status = "pending"
            persist(intent, actor, "ambiguous_payment_verification_requested")
            existing = IntegrationJob.objects.filter(event_key=f"gateway:verify:{intent.reference}").first()
            if existing:
                if existing.status in {"queued", "retry", "processing"}:
                    return existing
                return retry_job(actor=actor, record_id=existing.pk, expected_version=existing.version)
            return queue_verification(intent)
        intent.status, intent.error_code = "pending" if job.operation == "gateway_verify" else "created", ""
        persist(intent, actor, "gateway_retry_requested")
    job.status, job.attempts, job.next_attempt_at, job.lease_until, job.lease_token, job.error_code = "queued", 0, timezone.now(), None, None, ""
    persist(job, actor, "integration_manually_requeued")
    schedule(job)
    return job


@transaction.atomic
def recheck_intent(*, actor, record_id, expected_version=None):
    require_permission(actor, "integrations.change_gatewayintent")
    require_admin(actor)
    intent = GatewayIntent.objects.select_for_update().get(pk=record_id)
    validate_version(intent, expected_version)
    if intent.payment_id or intent.status not in {"review", "pending"}:
        raise ValidationError("Only unallocated pending/review payments can be checked again.")
    intent.status, intent.error_code = "pending", ""
    persist(intent, actor, "provider_recheck_requested")
    return enqueue(actor=actor, connection=intent.connection, operation="gateway_verify", event_key=f"gateway:manual:{intent.reference}:{intent.version}", payload={"intent_id": intent.pk})
