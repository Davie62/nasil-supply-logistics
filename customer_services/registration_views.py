from django.contrib import messages
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .forms import RegistrationForm, VerificationForm
from .models import RegistrationVerification
from .registration import register_customer, complete_registration, resend_code, code_preview_enabled
from .security import private_response, allow_request
from .views import limited


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return private_response(render(request, "portal/registration_session.html", {"staff_session": request.user.is_staff}))
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not allow_request(request, "customer-registration", 10, 3600):
            return limited()
        if form.is_valid():
            try:
                verification, code = register_customer(**{name: form.cleaned_data[name] for name in ("full_name", "email", "phone", "company_name", "username")}, password=form.cleaned_data["password1"])
            except (ValidationError, IntegrityError) as error:
                form.add_error(None, error.messages if isinstance(error, ValidationError) else "These account details are unavailable. Sign in or contact NASIL support.")
            else:
                request.session.cycle_key()
                request.session["registration_id"] = verification.pk
                if code_preview_enabled():
                    request.session["registration_code_preview"] = code
                return redirect("portal_verify_email")
    return private_response(render(request, "portal/register.html", {"form": form}))


@require_http_methods(["GET", "POST"])
def verify_email(request):
    if request.user.is_authenticated:
        return redirect("dashboard" if request.user.is_staff else "portal_dashboard")
    identifier = request.session.get("registration_id")
    if not identifier:
        return redirect("portal_register")
    verification = get_object_or_404(RegistrationVerification.objects.select_related("user"), pk=identifier, completed_at__isnull=True)
    form = VerificationForm(request.POST if request.method == "POST" and request.POST.get("action") != "resend" else None)
    if request.method == "POST":
        if not allow_request(request, "registration-verification", 30, 600):
            return limited()
        if request.POST.get("action") == "resend":
            if not allow_request(request, "registration-resend", 3, 3600):
                return limited()
            try:
                code = resend_code(verification_id=identifier)
            except ValidationError as error:
                form.add_error(None, error.messages)
            else:
                if code_preview_enabled():
                    request.session["registration_code_preview"] = code
                messages.success(request, "A new verification code has been requested. Use the latest code.")
                return redirect("portal_verify_email")
        elif form.is_valid():
            try:
                access = complete_registration(verification_id=identifier, code=form.cleaned_data["code"])
            except (ValidationError, IntegrityError) as error:
                form.add_error(None, error.messages if isinstance(error, ValidationError) else "This account cannot be activated. Contact NASIL support.")
            else:
                request.session.pop("registration_id", None)
                request.session.pop("registration_code_preview", None)
                login(request, access.user, backend="django.contrib.auth.backends.ModelBackend")
                request.session.set_expiry(0)
                messages.success(request, "Your customer account is ready. Welcome to NASIL.")
                return redirect("portal_dashboard")
    email = verification.user.email
    local, domain = email.rsplit("@", 1)
    return private_response(render(request, "portal/verify_email.html", {"form": form, "masked_email": local[:2] + "***@" + domain,
        "development_code": request.session.get("registration_code_preview") if code_preview_enabled() else None}))
