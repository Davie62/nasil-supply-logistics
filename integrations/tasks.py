import logging
import uuid
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from operations.commercial import persist
from .models import IntegrationJob, GatewayIntent
from .http import IntegrationError
from .adapters import OdooAdapter, FlutterwaveAdapter, PawaPayAdapter
from .services import queue_verification, settle_intent


@transaction.atomic
def claim(job_id):
    job = IntegrationJob.objects.select_for_update().select_related("connection", "requested_by").filter(pk=job_id).first()
    if not job or job.status in {"succeeded", "failed"} or (job.status == "processing" and job.lease_until and job.lease_until > timezone.now()) or job.next_attempt_at > timezone.now():
        return None
    job.status, job.lease_token, job.lease_until = "processing", uuid.uuid4(), timezone.now()+timedelta(minutes=5)
    job.attempts += 1
    persist(job, job.requested_by, "integration_claimed")
    return job


@shared_task
def run_job(job_id):
    if not settings.INTEGRATIONS_DELIVERY_ENABLED:
        return "disabled"
    job = claim(job_id)
    if not job:
        return "not_due"
    try:
        if not job.connection.is_active:
            raise IntegrationError("connection_disabled")
        if job.operation in {"invoice", "invoice_void", "purchase_order", "purchase_void"}:
            from payments.models import Invoice
            from procurement.models import PurchaseOrder
            source = Invoice.objects.get(reference=job.payload["reference"]) if job.operation.startswith("invoice") else PurchaseOrder.objects.get(reference=job.payload["reference"])
            if job.operation == "invoice" and source.status != "issued" or job.operation == "purchase_order" and source.status == "cancelled":
                raise IntegrationError("source_document_cancelled")
            adapter = OdooAdapter(job.connection)
            result = adapter.sync(job.operation, job.payload)
            if job.operation in {"invoice", "purchase_order"}:
                source.refresh_from_db()
                if source.status in {"void", "cancelled"}:
                    adapter.sync("invoice_void" if job.operation == "invoice" else "purchase_void", job.payload)
        else:
            intent = GatewayIntent.objects.select_related("invoice__quote__customer", "connection").get(pk=job.payload["intent_id"])
            if intent.status in {"succeeded", "failed", "review"}:
                result = intent.status
            else:
                adapter = FlutterwaveAdapter() if intent.connection.code == "flutterwave" else PawaPayAdapter()
                if job.operation == "gateway_init":
                    checkout_url = adapter.initiate(intent)
                    with transaction.atomic():
                        current = GatewayIntent.objects.select_for_update().get(pk=intent.pk)
                        current.status, current.checkout_url = "pending", checkout_url
                        persist(current, current.created_by, "payment_provider_accepted")
                        queue_verification(current)
                    result = "provider_accepted"
                else:
                    result = settle_intent(intent.pk, adapter.verify(intent))
    except (IntegrationError, ValidationError, PermissionDenied, ValueError, KeyError, TypeError) as error:
        code = error.code if isinstance(error, IntegrationError) else "integration_validation_failed"
        maximum = 288 if job.operation == "gateway_verify" else 4
        retry = isinstance(error, IntegrationError) and error.retryable and job.attempts < maximum
        with transaction.atomic():
            current = IntegrationJob.objects.select_for_update().get(pk=job.pk)
            if current.lease_token != job.lease_token:
                return "lease_lost"
            current.status, current.error_code, current.lease_until = "retry" if retry else "failed", code, None
            current.next_attempt_at = timezone.now()+timedelta(seconds=min(300, 60 * 2**min(job.attempts-1, 3)))
            persist(current, job.requested_by, "integration_retry" if retry else "integration_failed", error_code=code)
            if not retry and job.operation.startswith("gateway"):
                intent = GatewayIntent.objects.select_for_update().get(pk=job.payload["intent_id"])
                if not intent.payment_id:
                    intent.status, intent.error_code = "review", code
                    persist(intent, intent.created_by, "gateway_requires_review")
        logging.getLogger(__name__).warning("Integration job %s: %s", job.reference, code)
        return "retry" if retry else "failed"
    with transaction.atomic():
        current = IntegrationJob.objects.select_for_update().get(pk=job.pk)
        if current.lease_token != job.lease_token:
            return "lease_lost"
        current.status, current.remote_reference, current.lease_until, current.error_code = "succeeded", str(result), None, ""
        persist(current, job.requested_by, "integration_succeeded")
    return "succeeded"


@shared_task
def dispatch_jobs():
    if not settings.INTEGRATIONS_DELIVERY_ENABLED:
        return 0
    jobs = IntegrationJob.objects.filter(next_attempt_at__lte=timezone.now()).filter(Q(status__in=["queued", "retry"]) | Q(status="processing", lease_until__lt=timezone.now())).order_by("next_attempt_at")[:100]
    for job in jobs:
        run_job.delay(job.pk)
    return len(jobs)
