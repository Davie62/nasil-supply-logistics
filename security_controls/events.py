import logging
import uuid
from contextvars import ContextVar
from datetime import timedelta
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .network import ip_fingerprint

current_request = ContextVar("security_request", default=None)
logger = logging.getLogger("nasil.security")


def security_event(code, *, request=None, user=None, level="info", target_id=None):
    from .models import SecurityEvent, SecurityAlert
    request = request or current_request.get()
    user = user or getattr(request, "user", None)
    actor_id = user.pk if user and user.is_authenticated else None
    fingerprint = ip_fingerprint(request) if request else ""
    route = getattr(getattr(request, "resolver_match", None), "view_name", "") or ""
    request_id = getattr(request, "security_request_id", "") if request else ""
    data = {"code": code, "level": level, "actor_id": actor_id, "target_id": target_id,
            "ip_fingerprint": fingerprint, "request_id": request_id, "route": route[:100]}
    logger.log(logging.WARNING if level == "warning" else logging.INFO, code, extra={"security_data": data})
    try:
        with transaction.atomic():
            event = SecurityEvent.objects.create(**data)
            suspicious = level == "warning" and code in {"login_failed", "mfa_failed", "permission_denied", "request_rejected", "rate_limited", "reauthentication_failed", "csrf_rejected", "portal_access_denied"}
            threshold = suspicious and SecurityEvent.objects.filter(code=code, ip_fingerprint=fingerprint, created_at__gte=timezone.now()-timedelta(minutes=10)).count() >= 5
            if threshold or code in {"privileges_changed", "mfa_recovery_used", "mfa_operator_reset"}:
                bucket = int(timezone.now().timestamp()) // 600
                key = salted_hmac("nasil-security-alert", f"{code}:{fingerprint}:{actor_id}:{bucket}").hexdigest()
                _, created = SecurityAlert.objects.get_or_create(fingerprint=key, defaults={"code": code, "event": event})
                if created:
                    logger.warning("security_alert", extra={"security_data": {**data, "code": "security_alert", "event_reference": str(event.reference)}})
            return event
    except DatabaseError:
        # Bootstrap/migration failures still produce redacted centralized logs.
        logger.error("security_event_storage_unavailable", extra={"security_data": {"code": "security_event_storage_unavailable", "request_id": request_id}})
        return None
