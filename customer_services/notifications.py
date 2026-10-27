"""Transactional outbox; provider calls never run in Django save signals."""
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from .models import CustomerAccess, CustomerNotification, NotificationPreference


def recipient_for(customer, kind):
    access = CustomerAccess.objects.select_related("user").filter(customer=customer, enabled=True).first()
    if not access and kind == "password_reset":
        from .models import RegistrationVerification
        pending = RegistrationVerification.objects.select_related("user").filter(customer=customer, completed_at__isnull=True,
            user__is_staff=False, user__is_superuser=False, user__is_active=True, user__is_verified=False, user__email__iexact=customer.email).first()
        if pending:
            return "email", pending.user.email, ""
    if not access or access.user.is_staff or not access.user.is_active or not access.user.is_verified:
        return "email", "", "no_verified_access"
    if kind == "password_reset":
        verified = customer.email.lower() == access.verified_email.lower() == access.user.email.lower()
        return "email", access.verified_email if verified else "", "" if verified else "email_changed_requires_verification"
    preference = NotificationPreference.objects.filter(customer=customer).first()
    if preference:
        category = "quotation_updates" if kind == "quote_approved" else "delivery_updates" if kind in {"delivery_confirmed", "proof_available"} else "shipment_updates"
        if not preference.enabled or (kind != "invoice_issued" and not getattr(preference, category)):
            return preference.preferred_channel, "", "preference_disabled"
        if preference.preferred_channel == "sms":
            if not preference.sms_consent or not preference.sms_number:
                return "sms", "", "sms_consent_required"
            return "sms", preference.sms_number, ""
    if customer.email.lower() != access.verified_email.lower() or access.user.email.lower() != access.verified_email.lower():
        return "email", "", "email_changed_requires_verification"
    return "email", access.verified_email, ""


def schedule(notification):
    if not settings.NOTIFICATIONS_DELIVERY_ENABLED or notification.status != "queued":
        return
    def publish():
        try:
            from .tasks import deliver_notification
            deliver_notification.delay(notification.pk)
        except Exception:
            # Beat/dispatch command recovers from broker downtime. Never log credentials,
            # recipients, tokens, payloads or provider response bodies.
            import logging
            logging.getLogger(__name__).warning("Customer outbox publication deferred: %s", notification.reference)
    transaction.on_commit(publish)


def enqueue_event(audit):
    shipment = audit.shipment if audit.shipment_id else None
    quote = audit.quote
    if shipment:
        if audit.action == "delivery_proof_recorded":
            kind, title = "proof_available", "Your delivery proof is available"
        elif audit.to_status == "delivered" and audit.from_status != "delivered":
            kind, title = "delivery_confirmed", "Delivery confirmed"
        elif audit.action == "converted_from_quote" or (audit.action == "status_changed" and audit.from_status != audit.to_status) or (audit.action == "updated" and {"current_location", "estimated_delivery"} & set(audit.changes)):
            kind, title = "shipment_update", "Shipment update"
        else:
            return None
        link = reverse("portal_shipment", args=[shipment.pk])
        reference, status = shipment.tracking_number, shipment.get_status_display()
    elif audit.to_status == "approved" and audit.from_status != "approved" and audit.action == "status_changed":
        kind, title = "quote_approved", "Your quotation has been approved"
        link, reference, status = reverse("portal_quote", args=[quote.pk]), quote.quote_number, "Approved"
    else:
        return None
    channel, recipient, suppression = recipient_for(quote.customer, kind)
    body = render_to_string(f"notifications/{kind}.txt", {"reference": reference, "status": status}).strip()
    notification, created = CustomerNotification.objects.get_or_create(event_key=f"audit:{audit.pk}", defaults={
        "customer": quote.customer, "audit": audit, "kind": kind, "title": title, "body": body, "link": link,
        "channel": channel, "recipient": recipient, "status": "suppressed" if suppression else "queued", "last_error": suppression,
    })
    if created:
        schedule(notification)
    return notification


def enqueue_invitation(invitation):
    notification = CustomerNotification.objects.create(customer=invitation.customer, invitation=invitation, event_key=f"invite:{invitation.reference}",
        kind="invitation", title="Your NASIL customer portal invitation", body="Activate your secure NASIL customer account.", channel="email", recipient=invitation.email)
    schedule(notification)
    return notification


def enqueue_invoice(invoice):
    channel, recipient, suppression = recipient_for(invoice.quote.customer, "invoice_issued")
    body = render_to_string("notifications/invoice_issued.txt", {"reference": invoice.number, "currency": invoice.currency, "amount": invoice.amount}).strip()
    notification, created = CustomerNotification.objects.get_or_create(event_key=f"invoice:{invoice.reference}", defaults={
        "customer": invoice.quote.customer, "kind": "invoice_issued", "title": "Your invoice is available", "body": body,
        "link": reverse("portal_invoice", args=[invoice.pk]), "channel": channel, "recipient": recipient,
        "status": "suppressed" if suppression else "queued", "last_error": suppression,
    })
    if created:
        schedule(notification)
    return notification


def render_delivery(notification):
    context = {"title": notification.title, "body": notification.body, "reference": notification.reference}
    if notification.kind == "registration_verification":
        context["code"] = notification.payload["code"]
        return (render_to_string("notifications/registration_code.txt", context).strip(),
                render_to_string("notifications/registration_code.html", context), "")
    if notification.kind == "invitation":
        from .services import invitation_token
        path = reverse("portal_activate", args=[invitation_token(notification.invitation)])
    elif notification.kind == "password_reset":
        path = reverse("portal_reset_confirm", args=[notification.payload["uid"], notification.payload["token"]])
    else:
        path = notification.link
    context["url"] = settings.PUBLIC_SITE_URL + path if path else ""
    text = render_to_string("notifications/message.txt", context).strip()
    html = render_to_string("notifications/message.html", context)
    sms = render_to_string("notifications/message_sms.txt", context).strip()
    return text, html, sms
