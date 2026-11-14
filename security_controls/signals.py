import time
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models import F
from django.db.models.signals import pre_save, post_save, m2m_changed
from django.dispatch import receiver
from .events import security_event

User = get_user_model()


@receiver(user_logged_in)
def logged_in(sender, request, user, **kwargs):
    if request:
        from .models import MFAProfile
        profile, _ = MFAProfile.objects.get_or_create(user=user)
        request.session["security_session_generation"] = profile.revocation_version
        now = int(time.time())
        request.session["security_started_at"] = now
        request.session["security_last_seen"] = now
        for key in ("security_mfa_user", "security_mfa_version", "security_mfa_at", "security_pending_secret", "security_recovery_codes"):
            request.session.pop(key, None)
        maximum = settings.SECURITY_STAFF_SESSION_SECONDS if user.is_staff else settings.SECURITY_CUSTOMER_SESSION_SECONDS
        request.session.set_expiry(maximum if getattr(request, "POST", {}).get("remember_me") else 0)
    security_event("password_authenticated", request=request, user=user)


@receiver(user_login_failed)
def failed_login(sender, request=None, **kwargs):
    security_event("login_failed", request=request, level="warning")


@receiver(user_logged_out)
def logged_out(sender, request=None, user=None, **kwargs):
    security_event("logout", request=request, user=user)


@receiver(pre_save, sender=User)
def before_user_save(sender, instance, raw=False, **kwargs):
    if not raw and instance.pk:
        instance._security_before = sender.objects.filter(pk=instance.pk).values("is_staff", "is_superuser", "is_active", "password").first()


@receiver(post_save, sender=User)
def after_user_save(sender, instance, raw=False, **kwargs):
    previous = getattr(instance, "_security_before", None)
    if raw or not previous:
        return
    privileged = any(previous[key] != getattr(instance, key) for key in ("is_staff", "is_superuser", "is_active"))
    password_changed = previous["password"] != instance.password
    if privileged or password_changed:
        from .models import MFAProfile
        MFAProfile.objects.filter(user=instance).update(session_version=F("session_version")+1)
        security_event("privileges_changed" if privileged else "password_changed", target_id=instance.pk, level="warning" if privileged else "info")


@receiver(m2m_changed, sender=User.groups.through)
@receiver(m2m_changed, sender=User.user_permissions.through)
@receiver(m2m_changed, sender=Group.permissions.through)
def permissions_changed(sender, instance, action, **kwargs):
    if action == "post_add" and not kwargs.get("pk_set"):
        return
    if action.startswith("pre_"):
        targets = set(kwargs.get("pk_set") or [])
        if isinstance(instance, User):
            users = {instance.pk}
        elif isinstance(instance, Group):
            users = set(User.objects.filter(groups=instance).values_list("pk", flat=True))
            if sender is User.groups.through:
                users |= targets
        elif sender is User.user_permissions.through:
            users = set(User.objects.filter(user_permissions=instance).values_list("pk", flat=True)) | targets
        else:
            groups = set(Group.objects.filter(permissions=instance).values_list("pk", flat=True)) | targets
            users = set(User.objects.filter(groups__pk__in=groups).values_list("pk", flat=True))
        instance._security_affected_users = users
    if action in {"post_add", "post_remove", "post_clear"}:
        from .models import MFAProfile
        MFAProfile.objects.filter(user_id__in=getattr(instance, "_security_affected_users", [])).update(session_version=F("session_version")+1)
        security_event("privileges_changed", target_id=instance.pk, level="warning")
