from django.contrib import messages
from core.permissions import staff_permission_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import QuoteForm
from .models import Quote
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from core.business_rules import QUOTE_TRANSITIONS
from .workflows import create_quote, update_quote, transition_quote, EDITABLE_FIELDS
from operations.querysets import search, paginate


@staff_permission_required("quotations.view_quote")
def quotation_list(request):
	quotations = Quote.objects.select_related("customer", "service").order_by("-created_at")
	quotations = search(quotations, request.GET.get("q"), ("quote_number", "customer__full_name", "pickup_location", "destination"))
	active_filter = ""
	status = request.GET.get("status")
	if status in dict(Quote.STATUS_CHOICES):
		quotations = quotations.filter(status=status)
		active_filter = dict(Quote.STATUS_CHOICES)[status]
	page, pagination = paginate(request, quotations)
	rows = [
		{
			"values": [quote.quote_number, quote.customer.full_name, quote.status.title(), quote.created_at.strftime("%Y-%m-%d")],
			"url": f"/quotations/{quote.pk}/",
		}
		for quote in page
	]
	return render(request, "dashboard/workflow_list.html", {
		"title": "Quotations", "active_filter": active_filter, "clear_filter_url": "quotation_list",
		**pagination, "filter_choices": Quote.STATUS_CHOICES, "selected_status": status,
		"eyebrow": "COMMERCIAL",
		"description": "Create, review, and update customer quotation requests.",
		"columns": ["Reference", "Customer", "Status", "Created"],
		"rows": rows, "status_column": 2,
		"create_url": "quotation_create" if request.user.has_perm("quotations.add_quote") else None,
		"create_label": "New quotation",
	})


@staff_permission_required("quotations.view_quote", "quotations.add_quote")
def quotation_create(request):
	form = QuoteForm(request.POST or None)
	if form.is_valid():
		try:
			create_quote(actor=request.user, data={key: value for key, value in form.cleaned_data.items() if key in EDITABLE_FIELDS})
		except ValidationError as error:
			form.add_error(None, error.messages)
		else:
			messages.success(request, "Quotation created successfully.")
			return redirect("quotation_list")
	return render(request, "dashboard/workflow_form.html", {
		"title": "New quotation",
		"eyebrow": "COMMERCIAL",
		"form": form,
		"back_url": "quotation_list",
	})


@staff_permission_required("quotations.view_quote")
def quotation_update(request, pk):
	if request.method == "POST" and not request.POST.get("workflow_action") and not request.user.has_perm("quotations.change_quote"):
		raise PermissionDenied
	quotation = get_object_or_404(Quote, pk=pk)
	workflow_errors = []
	can_edit = request.user.has_perm("quotations.change_quote")
	form = QuoteForm(request.POST if request.method == "POST" and not request.POST.get("workflow_action") else None, instance=quotation)
	if request.method == "POST" and request.POST.get("workflow_action"):
		try:
			version = int(request.POST.get("record_version", ""))
			transition_quote(quote_id=pk, actor=request.user, target=request.POST["workflow_action"], reason=request.POST.get("reason", ""), expected_version=version)
		except (ValueError, ValidationError) as error:
			workflow_errors = error.messages if isinstance(error, ValidationError) else ["Reload the page before changing status."]
		else:
			messages.success(request, "Quotation status updated.")
			return redirect("quotation_update", pk=pk)
	elif request.method == "POST" and form.is_valid():
		try:
			update_quote(quote_id=pk, actor=request.user, data={key: value for key, value in form.cleaned_data.items() if key in EDITABLE_FIELDS}, expected_version=form.cleaned_data["record_version"])
		except ValidationError as error:
			form.add_error(None, error.messages)
		else:
			messages.success(request, "Quotation updated successfully.")
			return redirect("quotation_list")
	quotation.refresh_from_db()
	read_only = not can_edit or quotation.status == "approved" or hasattr(quotation, "shipment") or hasattr(quotation, "invoice")
	if read_only:
		for field in form.fields.values():
			field.disabled = True
	return render(request, "dashboard/workflow_form.html", {
		"title": f"Edit {quotation.quote_number}",
		"eyebrow": "COMMERCIAL",
		"form": form,
		"back_url": "quotation_list",
		"workflow_record": quotation, "audit_records": quotation.audit_records.select_related("actor")[:50],
		"workflow_errors": workflow_errors,
		"read_only": read_only,
		"workflow_actions": [key for key in sorted(QUOTE_TRANSITIONS.get(quotation.status, ())) if request.user.has_perm("quotations.approve_quote" if key == "approved" else "quotations.change_quote") and not hasattr(quotation, "shipment") and not hasattr(quotation, "invoice")],
		"conversion_url": "shipment_create" if quotation.status == "approved" and request.user.has_perm("shipments.add_shipment") else None,
	})
from django.shortcuts import render

# Create your views here.
