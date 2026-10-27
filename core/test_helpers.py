"""Business-valid fixtures shared by dashboard and workflow regression tests."""
from datetime import timedelta
from django.test import override_settings
from django.utils import timezone
from accounts.models import User
from quotations.workflows import create_quote, transition_quote
from shipments.workflows import convert_quote_to_shipment, transition_shipment


@override_settings(QUOTATION_APPROVAL_THRESHOLDS={"UGX": "1000000", "USD": "1000"})
def booked_shipment(customer, status="pending"):
    preparer, _ = User.objects.get_or_create(username="fixture-preparer", defaults={"email": "fixture-preparer@example.com", "is_staff": True, "is_superuser": True})
    approver, _ = User.objects.get_or_create(username="fixture-approver", defaults={"email": "fixture-approver@example.com", "is_staff": True, "is_superuser": True})
    quote = create_quote(actor=preparer, data={"customer": customer, "pickup_location": "Kampala", "destination": "Jinja", "cargo_description": "Goods", "weight": 10, "base_amount": 100, "valid_until": timezone.localdate() + timedelta(days=30)})
    transition_quote(quote_id=quote.pk, actor=preparer, target="reviewed")
    transition_quote(quote_id=quote.pk, actor=approver, target="approved")
    shipment = convert_quote_to_shipment(quote_id=quote.pk, actor=preparer)
    if status in {"in_transit", "delivered"}:
        shipment = transition_shipment(shipment_id=shipment.pk, actor=preparer, target="in_transit")
    if status in {"delivered", "cancelled"}:
        shipment = transition_shipment(shipment_id=shipment.pk, actor=preparer, target=status, reason="Fixture closure")
    return shipment
