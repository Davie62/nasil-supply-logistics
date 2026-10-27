from datetime import timedelta
import re
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from core.business_rules import require_permission
from customers.models import Customer
from operations.services import event
from .models import CustomerAccess, NotificationPreference, PortalInvitation

INVITATION_SALT = "nasil-customer-invitation-v1"


def invitation_token(invitation):
    return signing.dumps({"invitation": str(invitation.reference)}, salt=INVITATION_SALT)


def resolve_invitation(token):
    try:
        value = signing.loads(token, salt=INVITATION_SALT, max_age=7 * 86400)
        invitation = PortalInvitation.objects.select_related("customer").get(reference=value["invitation"])
    except (signing.BadSignature, PortalInvitation.DoesNotExist, ValueError, KeyError, TypeError):
        raise ValidationError("This invitation is invalid or expired.")
    if invitation.accepted_at or invitation.revoked_at or invitation.expires_at <= timezone.now() or invitation.email.lower() != invitation.customer.email.lower():
        raise ValidationError("This invitation is invalid or expired.")
    return invitation


@transaction.atomic
def invite_customer(*, actor, customer_id):
    require_permission(actor, "customer_services.manage_access", "customers.view_customer")
    customer = Customer.objects.select_for_update().get(pk=customer_id)
    if CustomerAccess.objects.filter(customer=customer).exists():
        raise ValidationError("This customer already has a portal account. Manage its access instead.")
    if User.objects.filter(email__iexact=customer.email).exists():
        raise ValidationError("An account with this email already exists. A superuser must reconcile that identity before inviting; accounts are never linked automatically.")
    PortalInvitation.objects.filter(customer=customer, accepted_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
    invitation = PortalInvitation.objects.create(customer=customer, email=customer.email.lower(), invited_by=actor, expires_at=timezone.now() + timedelta(days=7))
    from .notifications import enqueue_invitation
    enqueue_invitation(invitation)
    event(actor, "customer_access", customer.pk, "portal_invited", invitation=str(invitation.reference), expires_at=invitation.expires_at.isoformat())
    return invitation


@transaction.atomic
def activate_customer(*, token, username, password):
    original = resolve_invitation(token)
    customer = Customer.objects.select_for_update().get(pk=original.customer_id)
    invitation = PortalInvitation.objects.select_for_update().get(pk=original.pk)
    resolve_invitation(token)
    if CustomerAccess.objects.filter(customer=customer).exists() or User.objects.filter(email__iexact=invitation.email).exists() or User.objects.filter(username__iexact=username).exists():
        raise ValidationError("This invitation cannot create an account. Contact NASIL for help.")
    user = User(username=username, email=invitation.email, is_staff=False, is_superuser=False, is_verified=True)
    validate_password(password, user)
    user.set_password(password)
    user.full_clean()
    user.save()
    access = CustomerAccess.objects.create(customer=customer, user=user, verified_email=invitation.email)
    NotificationPreference.objects.get_or_create(customer=customer)
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    event(user, "customer_access", customer.pk, "portal_activated", invitation=str(invitation.reference))
    return access


@transaction.atomic
def set_access(*, actor, customer_id, enabled):
    require_permission(actor, "customer_services.manage_access", "customers.view_customer")
    access = CustomerAccess.objects.select_for_update().get(customer_id=customer_id)
    access.enabled = enabled
    access.save(update_fields=["enabled"])
    event(actor, "customer_access", customer_id, "portal_enabled" if enabled else "portal_revoked")
    return access


@transaction.atomic
def save_preferences(*, actor, data):
    access = CustomerAccess.objects.select_for_update().get(user=actor, enabled=True)
    if actor.is_staff or not actor.is_active or not actor.is_verified:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    allowed = {"preferred_channel", "sms_number", "sms_consent", "enabled", "quotation_updates", "shipment_updates", "delivery_updates"}
    if set(data) - allowed or data.get("preferred_channel") not in {"email", "sms"}:
        raise ValidationError("Choose valid notification preferences.")
    if data["preferred_channel"] == "sms" and data.get("enabled", True):
        if not re.fullmatch(r"\+[1-9]\d{7,14}", data.get("sms_number", "")) or not data.get("sms_consent"):
            raise ValidationError("SMS requires a phone number with country code and your consent.")
    preference, _ = NotificationPreference.objects.get_or_create(customer=access.customer)
    for key, value in data.items():
        setattr(preference, key, value)
    preference.full_clean()
    preference.save()
    event(actor, "customer_preferences", access.customer_id, "preferences_updated", channel=preference.preferred_channel, enabled=preference.enabled, sms_consent=preference.sms_consent)
    return preference
