from io import BytesIO
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from operations.exports import export_pdf
from operations.models import DeliveryProof
from operations.querysets import paginate, search
from operations.services import event
from payments.models import Invoice
from quotations.models import Quote
from shipments.models import Shipment
from .forms import ActivationForm, PortalLoginForm, PortalPasswordResetForm, PreferenceForm
from .models import CustomerNotification, NotificationPreference
from .notifications import recipient_for
from .security import allow_request, authenticate_portal, customer_required, private_response
from .services import activate_customer, resolve_invitation, save_preferences
from .tracking import public_projection


def limited():
    response = HttpResponse("Too many requests. Please try again later.", status=429)
    response["Retry-After"] = "60"
    return private_response(response)


@require_http_methods(["GET", "POST"])
def portal_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard" if request.user.is_staff else "portal_dashboard")
    form = PortalLoginForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not allow_request(request, "portal-login", 30, 600):
            return limited()
        if form.is_valid():
            user = authenticate_portal(request, **form.cleaned_data)
            if user:
                if not user.is_verified:
                    request.session["registration_id"] = user.registration_verification.pk
                    return redirect("portal_verify_email")
                login(request, user)
                request.session.set_expiry(60 * 60 * 24 * 30 if request.POST.get("remember_me") else 0)
                target = request.GET.get("next", "")
                if not target.startswith("/portal/") or not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    target = reverse("portal_dashboard")
                return redirect(target)
            form.add_error(None, "Unable to sign in. Check your credentials and portal access.")
    return private_response(render(request, "portal/login.html", {"title": "Customer login", "form": form, "login_page": True}))


@require_http_methods(["GET", "POST"])
def activate(request, token):
    if not allow_request(request, "portal-activation", 30, 3600):
        return limited()
    try:
        resolve_invitation(token)
    except ValidationError:
        raise Http404("This invitation is invalid or expired.")
    if request.user.is_authenticated:
        return private_response(render(request, "portal/activation_session.html", {
            "title": "Open this invitation as a customer",
            "staff_session": request.user.is_staff,
        }))
    form = ActivationForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        try:
            access = activate_customer(token=token, username=form.cleaned_data["username"], password=form.cleaned_data["password1"])
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error.messages if isinstance(error, ValidationError) else "Unable to activate this invitation. Contact NASIL.")
        else:
            login(request, access.user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("portal_dashboard")
    return private_response(render(request, "portal/auth.html", {"title": "Activate your customer portal", "form": form}))


@customer_required
@require_POST
def portal_logout(request):
    logout(request)
    return redirect("portal_login")


def visible_notifications(customer):
    return CustomerNotification.objects.filter(customer=customer).exclude(kind__in=["invitation", "password_reset", "registration_verification"])


@customer_required
@require_GET
def dashboard(request):
    quotes = Quote.objects.filter(customer=request.customer)
    shipments = Shipment.objects.filter(quote__customer=request.customer)
    invoices = Invoice.objects.filter(quote__customer=request.customer)
    return render(request, "portal/dashboard.html", {"title": "Your logistics overview", "quote_count": quotes.count(), "shipment_count": shipments.count(),
        "active_count": shipments.filter(status__in=["pending", "in_transit"]).count(), "invoice_count": invoices.count(),
        "shipments": shipments.order_by("-created_at", "-pk")[:5], "notifications": visible_notifications(request.customer)[:5]})


@customer_required
@require_GET
def quotation_list(request):
    queryset = search(Quote.objects.filter(customer=request.customer), request.GET.get("q"), ("quote_number", "destination"))
    page, context = paginate(request, queryset.order_by("-created_at", "-pk"))
    return render(request, "portal/list.html", {"title": "Your quotations", "kind": "quotes", "records": page, **context})


@customer_required
@require_GET
def quotation_detail(request, pk):
    quote = get_object_or_404(Quote.objects.filter(customer=request.customer), pk=pk)
    return render(request, "portal/quote.html", {"title": quote.quote_number, "quote": quote})


@customer_required
@require_GET
def shipment_list(request):
    queryset = search(Shipment.objects.filter(quote__customer=request.customer), request.GET.get("q"), ("tracking_number", "quote__destination"))
    page, context = paginate(request, queryset.order_by("-created_at", "-pk"))
    return render(request, "portal/list.html", {"title": "Your shipments", "kind": "shipments", "records": page, **context})


@customer_required
@require_GET
def shipment_detail(request, pk):
    shipment = get_object_or_404(Shipment.objects.select_related("quote").filter(quote__customer=request.customer), pk=pk)
    proof = DeliveryProof.objects.defer("evidence").filter(shipment=shipment).first()
    return render(request, "portal/shipment.html", {"title": shipment.tracking_number, "shipment": shipment, "tracking": public_projection(shipment), "proof": proof})


@customer_required
@require_GET
def invoice_list(request):
    queryset = search(Invoice.objects.filter(quote__customer=request.customer), request.GET.get("q"), ("number",))
    page, context = paginate(request, queryset.order_by("-issued_at", "-pk"))
    return render(request, "portal/list.html", {"title": "Your invoices", "kind": "invoices", "records": page, **context})


@customer_required
@require_GET
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("quote").filter(quote__customer=request.customer), pk=pk)
    from finance.services import balance_due
    from integrations.models import Connection
    return render(request, "portal/invoice.html", {"title": invoice.number, "invoice": invoice, "outstanding": balance_due(invoice),
        "payment_providers": Connection.objects.filter(is_active=True, code__in=["flutterwave", "pawapay"]) if settings.INTEGRATIONS_DELIVERY_ENABLED else [],
        "mobile_providers": settings.PAWAPAY_PROVIDERS})


def invoice_pdf_response(invoice, actor):
    from finance.services import paid_total, balance_due
    record = event(actor, "invoice", invoice.pk, "invoice_downloaded", reference=str(invoice.reference))
    return export_pdf(title="Invoice " + invoice.number, columns=["Description", "Value"], reference=record.reference, portrait=True,
        rows=[(key.replace("_", " ").title(), value) for key, value in invoice.pricing.items()],
        metadata=[("Invoice reference", str(invoice.reference)), ("Status", invoice.get_status_display()), ("Total", f"{invoice.currency} {invoice.amount}"), ("Payments recorded", f"{invoice.currency} {paid_total(invoice)}"), ("Outstanding", f"{invoice.currency} {balance_due(invoice)}"), ("Due date", str(invoice.due_date)), ("Issued", timezone.localtime(invoice.issued_at).isoformat(timespec="seconds")), ("Customer note", invoice.customer_note or "None")])


@customer_required
@require_GET
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.filter(quote__customer=request.customer), pk=pk)
    return invoice_pdf_response(invoice, request.user)


@customer_required
@require_GET
def evidence(request, pk):
    proof = get_object_or_404(DeliveryProof.objects.filter(shipment__quote__customer=request.customer), pk=pk)
    record = event(request.user, "proof", proof.pk, "customer_evidence_downloaded", proof_reference=str(proof.reference))
    response = FileResponse(BytesIO(bytes(proof.evidence)), as_attachment=True, filename=proof.evidence_name, content_type=proof.evidence_type)
    response["Content-Security-Policy"] = "sandbox"
    response["X-Audit-Reference"] = str(record.reference)
    return response


@customer_required
@require_GET
def notifications(request):
    page, context = paginate(request, visible_notifications(request.customer))
    return render(request, "portal/notifications.html", {"title": "Your notifications", "notifications": page, **context})


@customer_required
@require_POST
def notification_read(request, pk):
    notification = get_object_or_404(visible_notifications(request.customer), pk=pk)
    if not notification.read_at:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect("portal_notifications")


@customer_required
@require_http_methods(["GET", "POST"])
def preferences(request):
    preference = NotificationPreference.objects.filter(customer=request.customer).first() or NotificationPreference(customer=request.customer)
    form = PreferenceForm(request.POST if request.method == "POST" else None, instance=preference)
    if form.is_valid():
        try:
            save_preferences(actor=request.user, data=form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Your notification preferences were saved.")
            return redirect("portal_preferences")
    return render(request, "portal/preferences.html", {"title": "Notification preferences", "form": form, "verified_email": request.customer_access.verified_email})


@require_http_methods(["GET", "POST"])
def public_tracking(request, tracking_number=None):
    if not allow_request(request, "public-tracking", 60, 60):
        return limited()
    if request.method == "POST":
        reference = request.POST.get("tracking_number", "").strip().upper()
        import re
        if re.fullmatch(r"TRK-[A-Z0-9]{10,32}", reference):
            return redirect("public_tracking_result", tracking_number=reference)
        return private_response(render(request, "portal/tracking.html", {"title": "Track your shipment", "tracking_error": "Enter a valid NASIL tracking ID."}, status=400))
    context = {"title": "Track your shipment"}
    if tracking_number:
        shipment = get_object_or_404(Shipment.objects.only("pk", "tracking_number", "status", "created_at", "estimated_delivery"), tracking_number=tracking_number.upper())
        context["tracking"] = public_projection(shipment)
    return private_response(render(request, "portal/tracking.html", context))


class ResetRequestView(auth_views.PasswordResetView):
    template_name = "portal/auth.html"
    form_class = PortalPasswordResetForm
    success_url = reverse_lazy("portal_reset_sent")
    extra_context = {"title": "Reset your portal password"}

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and not allow_request(request, "portal-password-reset", 5, 3600):
            return limited()
        return private_response(super().dispatch(request, *args, **kwargs))
