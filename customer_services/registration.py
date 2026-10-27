"""Self-registration verifies the inbox before granting any customer-owned access."""
import secrets
import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from accounts.models import User
from customers.models import Customer
from operations.services import event
from .models import CustomerAccess, CustomerNotification, NotificationPreference, PortalInvitation, RegistrationVerification
from .notifications import schedule


def code_preview_enabled():
    return settings.DEBUG and not settings.NOTIFICATIONS_DELIVERY_ENABLED


def require_registration_delivery():
    if not code_preview_enabled() and not (settings.NOTIFICATIONS_DELIVERY_ENABLED and settings.SENDGRID_API_KEY and settings.DEFAULT_FROM_EMAIL):
        raise ValidationError("Account registration is temporarily unavailable. Please contact NASIL support.")


def replace_code(verification):
    code = f"{secrets.randbelow(1000000):06d}"
    verification.code_hash = make_password(code)
    verification.generation = uuid.uuid4()
    verification.expires_at = timezone.now() + timedelta(minutes=10)
    verification.sent_at = timezone.now()
    verification.attempts = 0
    verification.save()
    # Retain audit/delivery records but remove obsolete codes from their payloads.
    CustomerNotification.objects.filter(customer=verification.customer, kind="registration_verification", payload__verification_id=verification.pk).update(payload={})
    notification = CustomerNotification.objects.create(customer=verification.customer, event_key=f"register:{verification.generation}",
        kind="registration_verification", title="Verify your NASIL customer account", body="Verify your email address to complete account registration.",
        channel="email", recipient=verification.user.email,
        payload={"verification_id": verification.pk, "generation": str(verification.generation), "code": code})
    schedule(notification)
    return code


@transaction.atomic
def register_customer(*, full_name, email, phone, company_name, username, password):
    require_registration_delivery()
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=username).exists():
        raise ValidationError("An account with these details already exists. Sign in or contact NASIL support.")
    user = User(username=username, email=email, is_staff=False, is_superuser=False, is_verified=False)
    validate_password(password, user)
    user.set_password(password)
    user.full_clean()
    user.save()
    customer = Customer.objects.select_for_update().filter(email__iexact=email).first()
    if customer:
        if CustomerAccess.objects.filter(customer=customer).exists():
            raise ValidationError("This customer already has portal access. Sign in or contact NASIL support.")
    else:
        customer = Customer(full_name=full_name, email=email, phone=phone, company_name=company_name)
        customer.full_clean()
        customer.save()
    verification = RegistrationVerification(user=user, customer=customer)
    code = replace_code(verification)
    event(user, "customer_access", customer.pk, "registration_started")
    return verification, code


@transaction.atomic
def resend_code(*, verification_id):
    require_registration_delivery()
    verification = RegistrationVerification.objects.select_for_update().select_related("user").get(pk=verification_id)
    if verification.completed_at or verification.user.is_staff or not verification.user.is_active:
        raise ValidationError("This registration cannot be verified. Contact NASIL support.")
    if verification.sent_at > timezone.now() - timedelta(seconds=60):
        raise ValidationError("Please wait one minute before requesting another code.")
    return replace_code(verification)


def complete_registration(*, verification_id, code):
    # Commit failed-attempt counters before returning a validation error.
    error = None
    access = None
    with transaction.atomic():
        original = RegistrationVerification.objects.only("customer_id").get(pk=verification_id)
        Customer.objects.select_for_update().get(pk=original.customer_id)
        verification = RegistrationVerification.objects.select_for_update().select_related("user", "customer").get(pk=verification_id)
        user = User.objects.select_for_update().get(pk=verification.user_id)
        if verification.completed_at or verification.expires_at <= timezone.now() or verification.attempts >= 5:
            error = "This code has expired or is no longer valid. Request a new code."
        elif user.is_staff or not user.is_active or user.email.lower() != verification.customer.email.lower() or CustomerAccess.objects.filter(customer=verification.customer).exists():
            error = "This account cannot be activated. Contact NASIL support."
        elif not check_password(code, verification.code_hash):
            verification.attempts += 1
            verification.save(update_fields=["attempts"])
            error = "Incorrect verification code. Check your email and try again."
        else:
            user.is_verified = True
            user.save(update_fields=["is_verified"])
            access = CustomerAccess.objects.create(customer=verification.customer, user=user, verified_email=user.email)
            NotificationPreference.objects.get_or_create(customer=verification.customer)
            verification.completed_at = timezone.now()
            verification.code_hash = ""
            verification.save(update_fields=["completed_at", "code_hash"])
            PortalInvitation.objects.filter(customer=verification.customer, accepted_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
            CustomerNotification.objects.filter(customer=verification.customer, kind="registration_verification", payload__verification_id=verification.pk).update(payload={})
            event(user, "customer_access", verification.customer_id, "registration_verified")
    if error:
        raise ValidationError(error)
    return access


def verification_delivery_allowed(notification):
    payload = notification.payload
    return RegistrationVerification.objects.filter(pk=payload.get("verification_id"), generation=payload.get("generation"),
        customer_id=notification.customer_id, user__email__iexact=notification.recipient, customer__email__iexact=notification.recipient,
        user__is_staff=False, user__is_active=True, user__is_verified=False, completed_at__isnull=True,
        attempts__lt=5, expires_at__gt=timezone.now()).exists() if payload.get("verification_id") and payload.get("generation") else False
