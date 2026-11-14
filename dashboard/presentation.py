"""Presentation data shared by internal dashboard templates."""
from datetime import timedelta
from math import ceil

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from core.models import ContactMessage
from quotations.models import Quote
from shipments.models import Shipment


def operational_notifications(request):
    if hasattr(request, "_operational_notifications"):
        return request._operational_notifications
    items = []
    if request.user.has_perm("inventory.view_stocklevel"):
        from inventory.models import StockLevel
        from django.db.models import F
        low = StockLevel.objects.filter(product__is_active=True, item__is_active=True, item__quantity__lte=F("item__reorder_level")).count()
        if low:
            items.append({"label": "Low-stock alerts", "detail": "Warehouse stock is at or below reorder level", "count": low,
                          "url": reverse("inventory:stock_list") + "?low=1", "icon": "boxes", "tone": "warning"})
    from operations.policy import business_policy
    policy = business_policy()
    if request.user.has_perm("core.view_contactmessage") and (not policy or policy.notify_enquiries):
        count = ContactMessage.objects.filter(is_read=False).count()
        if count:
            items.append({"label": "Unread enquiries", "detail": "Customer messages need a response", "count": count,
                          "url": reverse("contact_message_list") + "?unread=1", "icon": "envelope", "tone": "info"})
    if request.user.has_perm("quotations.view_quote") and (not policy or policy.notify_quotations):
        count = Quote.objects.filter(status="pending").count()
        if count:
            items.append({"label": "Quotations to review", "detail": "New requests awaiting review", "count": count,
                          "url": reverse("quotation_list") + "?status=pending", "icon": "file-earmark-text", "tone": "warning"})
    if request.user.has_perm("shipments.view_shipment") and (not policy or policy.notify_overdue):
        count = Shipment.objects.filter(status__in=("pending", "in_transit"), estimated_delivery__lt=timezone.localdate()).count()
        if count:
            items.append({"label": "Overdue shipments", "detail": "Estimated delivery date has passed", "count": count,
                          "url": reverse("shipment_list") + "?overdue=1", "icon": "truck", "tone": "danger"})
    result = {"operational_notifications": items, "notification_count": sum(item["count"] for item in items)}
    request._operational_notifications = result
    return result


def shipment_bookings(days):
    """Count bookings by creation date, never infer historical delivery events."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    records = Shipment.objects.filter(created_at__date__gte=start, created_at__date__lte=today)
    daily_counts = dict(records.annotate(day=TruncDate("created_at")).values("day").annotate(total=Count("pk")).values_list("day", "total"))
    dates = [start + timedelta(days=offset) for offset in range(days)]
    values = [daily_counts.get(day, 0) for day in dates]
    step = max(1, ceil(max(values, default=0) / 4))
    maximum = step * 4
    points = " ".join(f"{40 + index * 580 / (days - 1):.2f},{180 - value * 160 / maximum:.2f}" for index, value in enumerate(values))
    indexes = sorted({0, (days - 1) // 4, (days - 1) // 2, (days - 1) * 3 // 4, days - 1})
    return {
        "total": sum(values), "average": sum(values) / days, "peak": max(values, default=0),
        "points": points, "area_points": "40,180 " + points + " 620,180",
        "grid": [{"y": 180 - index * 40, "label": step * index} for index in range(5)],
        "labels": [{"x": f"{40 + index * 580 / (days - 1):.2f}", "label": dates[index].strftime("%d %b")} for index in indexes],
    }
