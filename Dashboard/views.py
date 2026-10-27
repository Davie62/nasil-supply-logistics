from django.db.models import Count
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import EmployeeProfile
from core.permissions import staff_permission_required
from customers.models import Customer
from quotations.models import Quote
from shipments.models import Shipment
from .presentation import shipment_bookings


@staff_permission_required()
def dashboard(request):
    selected_range = request.GET.get("range", "30")
    if selected_range not in ("7", "30", "90"):
        selected_range = "30"
    context = {"selected_range": selected_range, "range_days": int(selected_range), "today": timezone.localdate()}
    if request.user.has_perm("shipments.view_shipment"):
        counts = dict(Shipment.objects.values("status").annotate(total=Count("pk")).values_list("status", "total"))
        status_counts = {status: counts.get(status, 0) for status in ("pending", "in_transit", "delivered", "cancelled")}
        total = sum(status_counts.values())
        stops, position = [], 0
        for status, color in (("pending", "--warning"), ("in_transit", "--info"), ("delivered", "--success"), ("cancelled", "--text-light")):
            end = position + (status_counts[status] * 100 / total if total else 0)
            stops.append(f"var({color}) {position:.2f}% {end:.2f}%")
            position = end
        context.update(
            shipment_count=total,
            delivery_rate=round(status_counts["delivered"] * 100 / total) if total else 0,
            shipment_trend=shipment_bookings(int(selected_range)),
            recent_shipments=Shipment.objects.select_related("quote__customer", "carrier").order_by("-created_at")[:6],
            status_breakdown=[{"code": status, "label": dict(Shipment.STATUS_CHOICES)[status], "count": count,
                               "share": round(count * 100 / total, 1) if total else 0}
                              for status, count in status_counts.items()],
            active_shipments=status_counts["pending"] + status_counts["in_transit"],
            status_counts=status_counts,
            shipment_gradient="conic-gradient(" + ", ".join(stops) + ")" if total else "var(--border-color, #e5e7eb)",
        )
    if request.user.has_perm("quotations.view_quote"):
        context["pending_quotes"] = Quote.objects.filter(status="pending").count()
    if request.user.has_perm("accounts.view_employeeprofile"):
        context["employee_count"] = EmployeeProfile.objects.filter(status="ACTIVE", user__is_active=True).count()
    if request.user.has_perm("customers.view_customer"):
        context["customer_count"] = Customer.objects.count()
    return render(request, "dashboard/dashboard.html", context)


@staff_permission_required()
def module_placeholder(request, module):
    if module == "shipments":
        return redirect("shipment_list")
    if module == "quotations":
        return redirect("quotation_list")
    if module == "employees":
        return redirect("staff_list")
    if module == "reports":
        return redirect("operations_reports")
    if module == "settings":
        return redirect("operations_settings")
    if module not in ("reports", "settings"):
        raise Http404
    return render(request, "dashboard/module_placeholder.html", {
        "title": module.title(), "eyebrow": "MANAGEMENT",
        "icon": "bi-hourglass-split", "status": "Planned",
        "description": f"The {module} module is planned and is not available yet.",
    })
