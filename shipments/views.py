from django.contrib import messages
from core.permissions import staff_permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ShipmentForm
from .models import Shipment
from django.core.exceptions import ValidationError
from .workflows import convert_quote_to_shipment, update_shipment
from operations.querysets import search, paginate


@staff_permission_required("shipments.view_shipment")
def shipment_list(request):
	shipments = Shipment.objects.select_related("quote__customer", "carrier").order_by("-created_at")
	shipments = search(shipments, request.GET.get("q"), ("tracking_number", "quote__customer__full_name", "quote__pickup_location", "quote__destination"))
	active_filter = ""
	status = request.GET.get("status")
	if status in dict(Shipment.STATUS_CHOICES):
		shipments = shipments.filter(status=status)
		active_filter = dict(Shipment.STATUS_CHOICES)[status]
	if request.GET.get("overdue") == "1":
		shipments = shipments.filter(status__in=("pending", "in_transit"), estimated_delivery__lt=timezone.localdate())
		active_filter = "Overdue shipments"
	page, pagination = paginate(request, shipments)
	rows = [
		{
			"values": [shipment.tracking_number, shipment.quote.customer.full_name, shipment.status.replace("_", " ").title(), shipment.carrier or "-", shipment.estimated_delivery.strftime("%d %b %Y") if shipment.estimated_delivery else "Not scheduled", f"{shipment.quote.pickup_location} to {shipment.quote.destination}"],
			"url": f"/shipments/{shipment.pk}/",
		}
		for shipment in page
	]
	return render(request, "dashboard/workflow_list.html", {
		"title": "Shipments", "active_filter": active_filter, "clear_filter_url": "shipment_list",
		**pagination, "filter_choices": Shipment.STATUS_CHOICES, "selected_status": status,
		"eyebrow": "OPERATIONS",
		"description": "Track consignments, delivery progress, and assigned carriers.",
		"columns": ["Tracking", "Customer", "Status", "Carrier", "Est. delivery", "Route"],
		"rows": rows, "status_column": 2,
		"create_url": "shipment_create" if request.user.has_perm("shipments.add_shipment") else None,
		"create_label": "New shipment",
	})


@staff_permission_required("shipments.view_shipment", "shipments.add_shipment", "quotations.view_quote")
def shipment_create(request):
	form = ShipmentForm(request.POST or None, initial={"quote": request.GET.get("quote")})
	if form.is_valid():
		try:
			convert_quote_to_shipment(actor=request.user, quote_id=form.cleaned_data["quote"].pk, **{key: form.cleaned_data[key] for key in ("carrier", "current_location", "estimated_delivery")})
		except ValidationError as error:
			form.add_error(None, error.messages)
		else:
			messages.success(request, "Approved quotation converted to a shipment.")
			return redirect("shipment_list")
	return render(request, "dashboard/workflow_form.html", {
		"title": "New shipment",
		"eyebrow": "OPERATIONS",
		"form": form,
		"back_url": "shipment_list",
	})


@staff_permission_required("shipments.view_shipment", "shipments.change_shipment")
def shipment_update(request, pk):
	shipment = get_object_or_404(Shipment, pk=pk)
	form = ShipmentForm(request.POST or None, instance=shipment)
	if form.is_valid():
		try:
			update_shipment(shipment_id=pk, actor=request.user, target=form.cleaned_data["status"], reason=form.cleaned_data["reason"], expected_version=form.cleaned_data["record_version"], **{key: form.cleaned_data[key] for key in ("carrier", "current_location", "estimated_delivery")})
		except ValidationError as error:
			form.add_error(None, error.messages)
		else:
			messages.success(request, "Shipment updated successfully.")
			return redirect("shipment_list")
	shipment.refresh_from_db()
	read_only = shipment.status in {"delivered", "cancelled"}
	if read_only:
		for field in form.fields.values():
			field.disabled = True
	return render(request, "dashboard/workflow_form.html", {
		"title": f"Edit {shipment.tracking_number}",
		"eyebrow": "OPERATIONS",
		"form": form,
		"back_url": "shipment_list",
		"workflow_record": shipment, "audit_records": shipment.history.select_related("actor")[:50],
		"read_only": read_only,
	})
from django.shortcuts import render

# Create your views here.
