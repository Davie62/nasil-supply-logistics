import hmac
import json
import os
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from customer_services.security import customer_required, allow_request
from operations.commercial import persist
from payments.models import Invoice
from .forms import IntentForm
from .models import GatewayIntent, Connection
from .services import create_intent, queue_verification


@customer_required
@require_POST
def customer_pay(request, pk):
    invoice = get_object_or_404(Invoice.objects.filter(quote__customer=request.customer), pk=pk)
    form = IntentForm({**request.POST.dict(), "invoice_id": pk})
    if not allow_request(request, "customer-payment-initiation", 10, 600):
        return HttpResponse("Too many payment requests. Try again later.", status=429)
    if form.is_valid():
        try:
            intent = create_intent(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            return redirect("integrations:customer_payment", reference=intent.reference)
    else:
        messages.error(request, "Choose a valid payment provider and payment details.")
    return redirect("portal_invoice", pk=invoice.pk)


@customer_required
@require_GET
def customer_payment(request, reference):
    intent = get_object_or_404(GatewayIntent.objects.select_related("invoice", "connection").filter(invoice__quote__customer=request.customer), reference=reference)
    return render(request, "portal/payment.html", {"intent": intent, "title": "Invoice payment"})


@csrf_exempt
@require_POST
def flutterwave_webhook(request):
    # Payloads only accelerate server-to-server verification; they never post money.
    secret = os.environ.get("FLUTTERWAVE_WEBHOOK_SECRET", "")
    if not settings.INTEGRATIONS_DELIVERY_ENABLED or not secret or not hmac.compare_digest(request.headers.get("verif-hash", ""), secret):
        return JsonResponse({"error": "Unauthorized"}, status=403)
    if not allow_request(request, "flutterwave-callback", 120, 60):
        return HttpResponse(status=429)
    if len(request.body) > 65536:
        return HttpResponse(status=413)
    try:
        data = json.loads(request.body).get("data", {})
        reference = data.get("tx_ref")
        from uuid import UUID
        reference = UUID(reference)
    except (ValueError, TypeError, AttributeError):
        return HttpResponse(status=400)
    with transaction.atomic():
        intent = GatewayIntent.objects.select_for_update().filter(reference=reference, connection__code="flutterwave", connection__is_active=True, status="pending").first()
        if intent:
            # Verification by our original tx_ref prevents callback ID substitution.
            queue_verification(intent)
    return JsonResponse({"received": True})
