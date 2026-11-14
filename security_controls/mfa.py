"""TOTP verification, replay prevention and single-use recovery codes."""
import re
import secrets
import time
from datetime import timedelta
import pyotp
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables
from .crypto import decrypt_secret
from .events import security_event
from .models import MFAProfile


@transaction.atomic
@sensitive_variables()
def verify_factor(user, code, *, enrolling_secret=None, request=None):
    profile, _ = MFAProfile.objects.select_for_update().get_or_create(user=user)
    if profile.locked_until and profile.locked_until > timezone.now():
        return None
    if enrolling_secret and profile.enabled:
        return None
    secret = enrolling_secret or profile.encrypted_secret
    if not secret:
        return None
    totp = pyotp.TOTP(decrypt_secret(secret))
    current = int(time.time()) // totp.interval
    matched = None
    if re.fullmatch(r"[0-9]{6}", code):
        for counter in (current-1, current, current+1):
            if counter > profile.last_counter and constant_time_compare(totp.at(counter * totp.interval), code):
                matched = counter
                break
    recovered = False
    if matched is None and not enrolling_secret:
        normalized = code.replace("-", "").lower()
        if re.fullmatch(r"[a-f0-9]{16}", normalized):
            for index, encoded in enumerate(profile.recovery_hashes):
                if check_password(normalized, encoded):
                    profile.recovery_hashes.pop(index)
                    recovered = True
                    break
    if matched is None and not recovered:
        profile.failed_attempts += 1
        if profile.failed_attempts >= 5:
            profile.locked_until = timezone.now()+timedelta(minutes=15)
        profile.save()
        security_event("mfa_failed", user=user, request=request, level="warning")
        return None
    profile.last_counter = matched if matched is not None else profile.last_counter
    profile.failed_attempts, profile.locked_until = 0, None
    codes = []
    if enrolling_secret:
        codes = [secrets.token_hex(8) for _ in range(10)]
        profile.encrypted_secret, profile.enabled = enrolling_secret, True
        profile.recovery_hashes = [make_password(code) for code in codes]
        profile.session_version += 1
    profile.save()
    security_event("mfa_enabled" if enrolling_secret else "mfa_recovery_used" if recovered else "mfa_verified", user=user, request=request, level="warning" if recovered else "info")
    return profile, codes


def mark_verified(request, profile):
    request.session.cycle_key()
    request.session["security_mfa_user"] = request.user.pk
    request.session["security_mfa_version"] = profile.session_version
    request.session["security_mfa_at"] = int(time.time())


def mfa_verified(request, profile):
    return request.session.get("security_mfa_user") == request.user.pk and request.session.get("security_mfa_version") == profile.session_version


def requires_mfa(user, profile):
    return bool(profile and profile.enabled) or (user.is_staff and settings.SECURITY_REQUIRE_STAFF_MFA)
