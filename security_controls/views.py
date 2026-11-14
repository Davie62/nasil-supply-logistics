import base64
import json
import time
from io import BytesIO
import pyotp
import qrcode
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.db import transaction
from .crypto import encrypt_secret, decrypt_secret
from .mfa import verify_factor, mark_verified, mfa_verified
from .models import MFAProfile
from .events import security_event


class CodeForm(forms.Form):
    code = forms.CharField(label="Authenticator or recovery code", max_length=40, widget=forms.TextInput(attrs={"class": "login-input", "autocomplete": "one-time-code", "autofocus": True}))


def destination(request):
    target = request.session.pop("security_next", "")
    if not target.startswith("/") or target.startswith("//") or "\\" in target or target.startswith("/security/"):
        return "dashboard" if request.user.is_staff else "portal_dashboard"
    return target


def pending_secret(request):
    encrypted = request.session.get("security_pending_secret", "")
    if not encrypted or int(time.time())-request.session.get("security_pending_at", 0) > 600:
        encrypted = encrypt_secret(pyotp.random_base32())
        request.session["security_pending_secret"] = encrypted
        request.session["security_pending_at"] = int(time.time())
    return encrypted


@login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("code")
@sensitive_variables("secret", "encrypted", "result")
def setup(request):
    profile = MFAProfile.objects.filter(user=request.user, enabled=True).first()
    if profile:
        return redirect("security_mfa_recovery" if mfa_verified(request, profile) and request.session.get("security_recovery_codes") else "security_mfa_challenge")
    encrypted = pending_secret(request)
    form = CodeForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        result = verify_factor(request.user, form.cleaned_data["code"], enrolling_secret=encrypted, request=request)
        if result:
            profile, codes = result
            mark_verified(request, profile)
            request.session.pop("security_pending_secret", None)
            request.session["security_recovery_codes"] = encrypt_secret(json.dumps(codes))
            return redirect("security_mfa_recovery")
        form.add_error("code", "Code not accepted. Check the time on your device or wait before retrying.")
    return render(request, "security/mfa.html", {"title": "Set up two-step verification", "form": form, "enrolling": True, "secret": decrypt_secret(encrypted)})


@login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("code")
def challenge(request):
    profile = MFAProfile.objects.filter(user=request.user, enabled=True).first()
    if not profile:
        return redirect("security_mfa_setup")
    if mfa_verified(request, profile):
        return redirect(destination(request))
    form = CodeForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        result = verify_factor(request.user, form.cleaned_data["code"], request=request)
        if result:
            mark_verified(request, result[0])
            return redirect(destination(request))
        form.add_error("code", "Code not accepted. Use a fresh code or an unused recovery code.")
    return render(request, "security/mfa.html", {"title": "Verify your sign-in", "form": form})


@login_required
@require_GET
def qr(request):
    if MFAProfile.objects.filter(user=request.user, enabled=True).exists():
        return HttpResponse(status=404)
    encrypted = request.session.get("security_pending_secret")
    if not encrypted or int(time.time())-request.session.get("security_pending_at", 0) > 600:
        return HttpResponse(status=404)
    uri = pyotp.TOTP(decrypt_secret(encrypted)).provisioning_uri(request.user.username, issuer_name="NASIL Supply & Logistics")
    output = BytesIO()
    qrcode.make(uri).save(output, format="PNG")
    return HttpResponse(output.getvalue(), content_type="image/png")


@login_required
@require_http_methods(["GET", "POST"])
def recovery(request):
    profile = MFAProfile.objects.filter(user=request.user, enabled=True).first()
    if not profile or not mfa_verified(request, profile):
        return redirect("security_mfa_challenge")
    if request.method == "POST":
        request.session.pop("security_recovery_codes", None)
        return redirect(destination(request))
    encrypted = request.session.get("security_recovery_codes")
    if not encrypted:
        return redirect(destination(request))
    return render(request, "security/recovery.html", {"codes": json.loads(decrypt_secret(encrypted))})


def csrf_failure(request, reason=""):
    security_event("csrf_rejected", request=request, level="warning")
    return HttpResponse("Security verification failed. Reload the form and try again.", status=403)


@login_required
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("password")
def account_security(request):
    profile, _ = MFAProfile.objects.get_or_create(user=request.user)
    form = forms.Form(request.POST if request.method == "POST" else None)
    form.fields["password"] = forms.CharField(label="Current password", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}), max_length=1024)
    if form.is_valid():
        if request.user.check_password(form.cleaned_data["password"]):
            with transaction.atomic():
                profile = MFAProfile.objects.select_for_update().get(user=request.user)
                profile.revocation_version += 1
                profile.save(update_fields=["revocation_version", "updated_at"])
                security_event("all_sessions_revoked", request=request)
            from django.contrib.auth import logout
            staff = request.user.is_staff
            logout(request)
            return redirect("login" if staff else "portal_login")
        security_event("reauthentication_failed", request=request, level="warning")
        form.add_error("password", "Password not accepted.")
    return render(request, "security/account.html", {"form": form, "mfa_enabled": profile.enabled})
