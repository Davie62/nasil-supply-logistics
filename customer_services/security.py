from functools import wraps
from datetime import timedelta
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac
from accounts.models import User
from core.constants import MAX_LOGIN_ATTEMPTS, ACCOUNT_LOCK_MINUTES
from .models import CustomerAccess, RateBucket, RegistrationVerification


def customer_required(view):
    @login_required(login_url="portal_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or not request.user.is_active:
            raise PermissionDenied
        access = CustomerAccess.objects.select_related("customer").filter(user=request.user, enabled=True).first()
        if not access or not request.user.is_verified:
            raise PermissionDenied
        request.customer_access = access
        request.customer = access.customer
        response = view(request, *args, **kwargs)
        return private_response(response)
    return wrapped


def private_response(response):
    response["Cache-Control"] = "private, no-store"
    # Preserve the same-origin Origin header on forms for Django CSRF checks;
    # suppress referrers entirely when navigating to another origin.
    response["Referrer-Policy"] = "same-origin"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@transaction.atomic
def allow_request(request, scope, limit, seconds):
    now = timezone.now()
    window = int(now.timestamp()) // seconds
    identity = request.META.get("REMOTE_ADDR", "unknown")[:100]
    key = salted_hmac("customer-services-rate", f"{scope}:{identity}:{window}").hexdigest()
    bucket, _ = RateBucket.objects.get_or_create(key=key, defaults={"expires_at": now + timedelta(seconds=seconds * 2)})
    return bool(RateBucket.objects.filter(pk=bucket.pk, count__lt=limit).update(count=F("count") + 1))


@transaction.atomic
def authenticate_portal(request, username, password):
    existing = User.objects.select_for_update().filter(username=username).first()
    user = authenticate(request, username=username, password=password)
    valid = user and not user.is_staff and (
        (user.is_verified and CustomerAccess.objects.filter(user=user, enabled=True).exists()) or
        (not user.is_verified and RegistrationVerification.objects.filter(user=user, completed_at__isnull=True).exists()))
    if existing and existing.locked_until and existing.locked_until > timezone.now():
        valid = False
    if valid:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until"])
        return user
    if existing:
        existing.failed_login_attempts += 1
        if existing.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            existing.locked_until = timezone.now() + timedelta(minutes=ACCOUNT_LOCK_MINUTES)
        existing.save(update_fields=["failed_login_attempts", "locked_until"])
    return None
