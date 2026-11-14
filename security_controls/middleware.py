import secrets
import time
import uuid
from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import ValidationError, SuspiciousOperation
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from .events import current_request, security_event
from .mfa import mfa_verified, requires_mfa
from .models import MFAProfile
from .validators import clean_text, positive_integer


class RequestGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.security_request_id = str(uuid.uuid4())
        request.csp_nonce = secrets.token_urlsafe(24)
        token = current_request.set(request)
        try:
            try:
                self.validate(request)
            except (ValidationError, SuspiciousOperation, ValueError):
                security_event("request_rejected", request=request, level="warning")
                response = HttpResponse("Invalid request parameters.", status=400)
            else:
                response = self.get_response(request)
            if response.status_code == 403:
                security_event("permission_denied", request=request, level="warning")
            response["X-Request-ID"] = request.security_request_id
            response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            policy = "default-src 'self'; script-src 'self' 'nonce-" + request.csp_nonce + "' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
            response["Content-Security-Policy"] = policy
            if request.path.startswith(("/security/", "/accounts/", "/admin/")) or getattr(getattr(request, "user", None), "is_authenticated", False):
                response["Cache-Control"] = "private, no-store"
            return response
        finally:
            current_request.reset(token)

    def validate(self, request):
        if len(request.META.get("QUERY_STRING", "")) > 8192 or len(request.GET) > 40:
            raise ValidationError("Query too large.")
        for key, values in request.GET.lists():
            clean_text(key, limit=100, multiline=False)
            if len(values) != 1:
                raise ValidationError("Duplicate query parameters.")
            clean_text(values[0], limit=150 if key == "q" else 2048, multiline=False)
            if key in {"page", "staff"} and values[0]:
                positive_integer(values[0], maximum=1000000000)
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.META.get("CONTENT_LENGTH", "")
            if length and (not length.isdigit() or int(length) > 8 * 1024 * 1024):
                raise ValidationError("Request body too large.")
            # Do not parse multipart bodies here: bounded upload validation owns files.
            if request.content_type == "application/x-www-form-urlencoded":
                for key, values in request.POST.lists():
                    clean_text(key, limit=150, multiline=False)
                    for value in values:
                        clean_text(value, limit=20000)


class AuthenticationGuardMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        from customer_services.security import allow_request
        name = request.resolver_match.view_name
        if request.method == "POST":
            scope = None
            if name in {"login", "admin:login"}:
                scope = ("staff-login", 30, 600)
            elif name in {"contact", "quote"}:
                scope = ("public-intake", 10, 600)
            elif name in {"security_mfa_setup", "security_mfa_challenge"}:
                scope = ("mfa-verification", 30, 600)
            elif name == "security_account":
                scope = ("security-reauthentication", 10, 600)
            if scope and not allow_request(request, *scope):
                security_event("rate_limited", request=request, level="warning")
                response = HttpResponse("Too many requests. Please try again later.", status=429)
                response["Retry-After"] = "600"
                return response
        if not request.user.is_authenticated:
            return None
        now = int(time.time())
        staff = request.user.is_staff
        maximum = settings.SECURITY_STAFF_SESSION_SECONDS if staff else settings.SECURITY_CUSTOMER_SESSION_SECONDS
        idle = settings.SECURITY_STAFF_IDLE_SECONDS if staff else settings.SECURITY_CUSTOMER_IDLE_SECONDS
        started = request.session.get("security_started_at", now)
        last = request.session.get("security_last_seen", now)
        if now-started >= maximum or now-last >= idle:
            security_event("session_expired", request=request)
            logout(request)
            return redirect("login" if staff else "portal_login")
        request.session.setdefault("security_started_at", now)
        request.session["security_last_seen"] = now
        profile = MFAProfile.objects.filter(user_id=request.user.pk).first()
        if profile and request.session.get("security_session_generation", profile.revocation_version) != profile.revocation_version:
            security_event("session_revoked", request=request)
            logout(request)
            return redirect("login" if staff else "portal_login")
        permitted = {"security_mfa_setup", "security_mfa_challenge", "security_mfa_qr", "security_mfa_recovery", "logout", "portal_logout", "admin:logout"}
        if requires_mfa(request.user, profile) and not (profile and profile.enabled and mfa_verified(request, profile)) and name not in permitted:
            # Store only a local path. POST bodies are never retained or replayed.
            request.session["security_next"] = request.path
            return redirect("security_mfa_challenge" if profile and profile.enabled else "security_mfa_setup")
        return None
