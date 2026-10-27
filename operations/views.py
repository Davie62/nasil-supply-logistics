from io import BytesIO

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery, Sum
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.models import EmployeeProfile
from core.models import AuditRecord
from core.permissions import staff_permission_required
from quotations.models import Quote
from shipments.models import Shipment
from .exports import export_csv, export_pdf
from .forms import DeliveryProofForm, InventoryForm, ReportFilterForm, SettingsForm, StaffForm, StockMovementForm
from .models import BusinessSettings, DeliveryProof, InventoryItem, OperationsEvent
from .querysets import date_range, paginate, search
from .services import deactivate_staff, event, move_stock, record_delivery_proof, require_admin, save_inventory, save_settings, save_staff


def action(name, label, pk=None):
    return {"url": reverse(name, args=[pk] if pk is not None else []), "label": label}


def detail(request, *, title, fields, actions=(), audit=None, **context):
    if audit is not None:
        page, paging = paginate(request, audit)
        context.update(audit_records=page, **paging)
    return render(request, "operations/detail.html", {"title": title, "fields": fields, "actions": actions, **context})


@staff_permission_required("quotations.view_quote")
@require_GET
def quotation_detail(request, pk):
    quote = get_object_or_404(Quote.objects.select_related("customer", "service", "approved_by", "prepared_by"), pk=pk)
    actions = []
    if request.user.has_perm("quotations.change_quote") or request.user.has_perm("quotations.approve_quote"):
        actions.append(action("quotation_update", "Manage quotation", pk))
    if request.user.has_perm("shipments.view_shipment") and hasattr(quote, "shipment"):
        actions.append(action("shipment_detail", "View shipment", quote.shipment.pk))
    return detail(request, title=quote.quote_number, back_url="quotation_list", actions=actions, audit=quote.audit_records.all(), fields=[
        ("Customer", quote.customer.full_name), ("Status", quote.get_status_display()), ("Service", quote.service or "Not assigned"),
        ("Pickup", quote.pickup_location), ("Destination", quote.destination), ("Cargo", quote.cargo_description),
        ("Weight (kg)", quote.weight), ("Trade scope", quote.get_trade_type_display()), ("Currency", quote.currency),
        ("Base amount", quote.base_amount), ("Rate per kg", quote.rate_per_kg), ("Surcharge", quote.surcharge),
        ("Discount", quote.discount), ("Subtotal", quote.subtotal), ("Tax", quote.tax_amount), ("Total", quote.total_amount),
        ("Valid until", quote.valid_until), ("Preparer", quote.prepared_by or "Legacy / public"),
        ("Approved by", quote.approved_by or "Not verified"), ("Approved at", quote.approved_at),
        ("Created", quote.created_at), ("Updated", quote.updated_at),
    ])


@staff_permission_required("shipments.view_shipment")
@require_GET
def shipment_detail(request, pk):
    shipment = get_object_or_404(Shipment.objects.select_related("quote__customer", "carrier", "created_by"), pk=pk)
    actions = []
    if request.user.has_perm("shipments.change_shipment"):
        actions.append(action("shipment_update", "Manage shipment", pk))
    if request.user.has_perm("quotations.view_quote"):
        actions.append(action("quotation_detail", "View quotation", shipment.quote_id))
    proof = DeliveryProof.objects.defer("evidence").filter(shipment=shipment).first()
    if proof and request.user.has_perm("operations.view_deliveryproof"):
        actions.append(action("proof_detail", "Delivery proof", proof.pk))
    elif not proof and shipment.status == "delivered" and request.user.has_perm("operations.add_deliveryproof"):
        actions.append(action("proof_create", "Record delivery proof", pk))
    return detail(request, title=shipment.tracking_number, back_url="shipment_list", actions=actions, audit=shipment.history.all(), fields=[
        ("Customer", shipment.quote.customer.full_name), ("Quotation", shipment.quote.quote_number), ("Status", shipment.get_status_display()),
        ("Pickup", shipment.quote.pickup_location), ("Destination", shipment.quote.destination), ("Current location", shipment.current_location),
        ("Carrier", shipment.carrier), ("Estimated delivery", shipment.estimated_delivery), ("Dispatched", shipment.dispatched_at),
        ("Delivered", shipment.delivered_at), ("Cancelled", shipment.cancelled_at), ("Booked by", shipment.created_by),
        ("Proof recorded", "Yes" if proof else "No"), ("Created", shipment.created_at), ("Updated", shipment.updated_at),
    ])


@staff_permission_required("operations.view_inventoryitem")
@require_GET
def inventory_list(request):
    items = search(InventoryItem.objects.select_related("warehouse__branch"), request.GET.get("q"), ("sku", "name", "warehouse__name"))
    status = request.GET.get("status", "")
    if status in {"active", "archived"}:
        items = items.filter(is_active=status == "active")
    page, context = paginate(request, items)
    return render(request, "dashboard/workflow_list.html", {
        "title": "Inventory", "eyebrow": "WAREHOUSE", "description": "Warehouse balances backed by an auditable receipt and issue ledger.",
        "columns": ["SKU", "Item", "Warehouse", "On hand", "Unit", "Status"], "status_column": 5,
        "rows": [{"values": [item.sku, item.name, item.warehouse.name, item.quantity, item.unit, "Active" if item.is_active else "Archived"], "url": reverse("inventory_detail", args=[item.pk])} for item in page],
        "create_url": "inventory_create" if request.user.has_perm("operations.add_inventoryitem") else None, "create_label": "New inventory item",
        "filter_choices": [("active", "Active"), ("archived", "Archived")], "selected_status": status, **context,
    })


def inventory_context(request, item, movement_form=None):
    events = OperationsEvent.objects.filter(entity_type="inventory", entity_id=str(item.pk))
    actions = [action("inventory_update", "Edit item", item.pk)] if request.user.has_perm("operations.change_inventoryitem") else []
    return detail(request, title=str(item), back_url="inventory_list", actions=actions, audit=events, fields=[
        ("Warehouse", item.warehouse.name), ("Branch", item.warehouse.branch.name), ("Unit", item.unit), ("On hand", item.quantity),
        ("Reorder level", item.reorder_level), ("Stock alert", "Reorder required" if item.quantity <= item.reorder_level else "Above reorder level"),
        ("Status", "Active" if item.is_active else "Archived"), ("Updated", item.updated_at),
    ], movement_form=movement_form or (StockMovementForm(initial={"record_version": item.version}) if item.is_active and request.user.has_perm("operations.adjust_inventory") else None),
        movement_url=reverse("inventory_move", args=[item.pk]), movements=item.movements.select_related("actor")[:25])


@staff_permission_required("operations.view_inventoryitem")
@require_GET
def inventory_detail(request, pk):
    return inventory_context(request, get_object_or_404(InventoryItem.objects.select_related("warehouse__branch"), pk=pk))


@staff_permission_required("operations.view_inventoryitem")
@require_http_methods(["GET", "POST"])
def inventory_edit(request, pk=None):
    permission = "operations.change_inventoryitem" if pk else "operations.add_inventoryitem"
    if not request.user.has_perm(permission):
        raise PermissionDenied
    item = get_object_or_404(InventoryItem, pk=pk) if pk else None
    form = InventoryForm(request.POST if request.method == "POST" else None, instance=item)
    if form.is_valid():
        data = form.cleaned_data.copy()
        version = data.pop("record_version", None)
        try:
            item = save_inventory(actor=request.user, item_id=pk, data=data, expected_version=version)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error.messages if isinstance(error, ValidationError) else "This warehouse SKU already exists.")
        else:
            return redirect("inventory_detail", pk=item.pk)
    return render(request, "dashboard/workflow_form.html", {"title": "Edit inventory item" if pk else "New inventory item", "eyebrow": "WAREHOUSE", "form": form, "back_url": "inventory_list"})


@staff_permission_required("operations.view_inventoryitem", "operations.adjust_inventory")
@require_POST
def inventory_move(request, pk):
    item = get_object_or_404(InventoryItem.objects.select_related("warehouse__branch"), pk=pk)
    form = StockMovementForm(request.POST)
    if form.is_valid():
        try:
            move_stock(actor=request.user, item_id=pk, quantity_change=form.cleaned_data["quantity_change"], reason=form.cleaned_data["reason"], expected_version=form.cleaned_data["record_version"])
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Stock movement recorded.")
            return redirect("inventory_detail", pk=pk)
    item.refresh_from_db()
    return inventory_context(request, item, form)


@staff_permission_required("accounts.view_employeeprofile")
@require_GET
def staff_list(request):
    staff = search(EmployeeProfile.objects.select_related("user", "department", "branch"), request.GET.get("q"), ("employee_id", "user__username", "user__first_name", "user__last_name", "user__email", "department__name"))
    status = request.GET.get("status", "")
    if status in dict(EmployeeProfile.STATUS):
        staff = staff.filter(status=status)
    page, context = paginate(request, staff)
    return render(request, "dashboard/workflow_list.html", {"title": "Staff", "eyebrow": "PEOPLE", "description": "Manage staff records, assignments and account lifecycle.",
        "columns": ["Employee ID", "Name", "Department", "Position", "Status"], "status_column": 4,
        "rows": [{"values": [profile.employee_id, profile.user.get_full_name() or profile.user.username, profile.department.name, profile.position, profile.get_status_display()], "url": reverse("staff_detail", args=[profile.pk])} for profile in page],
        "create_url": "staff_create" if request.user.has_perm("accounts.add_employeeprofile") else None, "create_label": "Add staff member", "filter_choices": EmployeeProfile.STATUS, "selected_status": status, **context})


@staff_permission_required("accounts.view_employeeprofile")
@require_GET
def staff_detail(request, pk):
    profile = get_object_or_404(EmployeeProfile.objects.select_related("user", "department", "branch"), pk=pk)
    actions = []
    if request.user.has_perm("accounts.change_employeeprofile"):
        actions.append(action("staff_update", "Edit staff member", pk))
    if request.user.has_perm("accounts.delete_employeeprofile") and profile.user.is_active:
        actions.append(action("staff_delete", "Deactivate account", pk))
    if request.user.is_superuser:
        actions.append(action("admin:accounts_user_change", "Manage account roles", profile.user_id))
    return detail(request, title=profile.user.get_full_name() or profile.user.username, back_url="staff_list", actions=actions,
        audit=OperationsEvent.objects.filter(entity_type="staff", entity_id=str(pk)), fields=[
            ("Employee ID", profile.employee_id), ("Username", profile.user.username), ("Email", profile.user.email),
            ("Phone", profile.phone_number), ("Department", profile.department.name), ("Branch", profile.branch.name),
            ("Position", profile.position), ("Hire date", profile.hire_date), ("Status", profile.get_status_display()),
            ("Login enabled", "Yes" if profile.user.is_active else "No"), ("Roles", ", ".join(profile.user.groups.values_list("name", flat=True)) or "No roles assigned"),
            ("Updated", profile.updated_at),
        ])


@staff_permission_required("accounts.view_employeeprofile")
@require_http_methods(["GET", "POST"])
def staff_edit(request, pk=None):
    if not request.user.has_perm("accounts.change_employeeprofile" if pk else "accounts.add_employeeprofile"):
        raise PermissionDenied
    profile = get_object_or_404(EmployeeProfile.objects.select_related("user"), pk=pk) if pk else None
    if profile:
        from .services import guard_staff_target
        guard_staff_target(request.user, profile.user)
    form = StaffForm(request.POST if request.method == "POST" else None, profile=profile)
    if profile and not request.user.is_superuser:
        for name in ("username", "email", "password"):
            form.fields[name].disabled = True
        form.fields["password"].help_text = "Only a superuser may reset an existing staff password."
    if form.is_valid():
        data = form.cleaned_data.copy()
        version = data.pop("record_version", None)
        try:
            profile = save_staff(actor=request.user, data=data, profile_id=pk, expected_version=version)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error.messages if isinstance(error, ValidationError) else "Username, email or phone is already in use.")
        else:
            messages.success(request, "Staff member saved. Roles are assigned separately by a superuser.")
            return redirect("staff_detail", pk=profile.pk)
    return render(request, "dashboard/workflow_form.html", {"title": "Edit staff member" if pk else "Add staff member", "eyebrow": "PEOPLE", "form": form, "back_url": "staff_list"})


class DeactivateForm(forms.Form):
    reason = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}))
    record_version = forms.CharField(widget=forms.HiddenInput)


@staff_permission_required("accounts.view_employeeprofile", "accounts.delete_employeeprofile")
@require_http_methods(["GET", "POST"])
def staff_deactivate(request, pk):
    profile = get_object_or_404(EmployeeProfile.objects.select_related("user"), pk=pk)
    from .services import guard_staff_target
    guard_staff_target(request.user, profile.user)
    form = DeactivateForm(request.POST if request.method == "POST" else None, initial={"record_version": profile.updated_at.isoformat()})
    if form.is_valid():
        try:
            deactivate_staff(actor=request.user, profile_id=pk, **{("expected_version" if key == "record_version" else key): value for key, value in form.cleaned_data.items()})
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("staff_detail", pk=pk)
    return render(request, "dashboard/workflow_form.html", {"title": "Deactivate " + profile.user.username, "eyebrow": "Disables login and retains employment and audit records", "form": form, "back_url": "staff_list"})


@staff_permission_required("operations.view_businesssettings")
@require_http_methods(["GET", "POST"])
def settings_view(request):
    require_admin(request.user)
    policy = BusinessSettings.objects.filter(pk=1).first() or BusinessSettings(
        ugx_approval_threshold=settings.QUOTATION_APPROVAL_THRESHOLDS.get("UGX", 50000000),
        usd_approval_threshold=settings.QUOTATION_APPROVAL_THRESHOLDS.get("USD", 15000))
    form = SettingsForm(request.POST if request.method == "POST" else None, instance=policy, initial={"record_version": policy.version})
    if request.method == "POST" and not request.user.has_perm("operations.change_businesssettings"):
        raise PermissionDenied
    if form.is_valid():
        data = form.cleaned_data.copy()
        version = data.pop("record_version")
        try:
            save_settings(actor=request.user, data=data, expected_version=version)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            messages.success(request, "Business settings updated. Existing quotation currencies are preserved.")
            return redirect("operations_settings")
    if not request.user.has_perm("operations.change_businesssettings"):
        for field in form.fields.values():
            field.disabled = True
    return render(request, "dashboard/workflow_form.html", {"title": "Business settings", "eyebrow": "Administrator policy · Changes apply immediately · Currency choices affect new work", "form": form, "back_url": "dashboard", "read_only": not request.user.has_perm("operations.change_businesssettings")})


@staff_permission_required("operations.add_deliveryproof", "shipments.view_shipment")
@require_http_methods(["GET", "POST"])
def proof_create(request, pk):
    shipment = get_object_or_404(Shipment, pk=pk)
    form = DeliveryProofForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if form.is_valid():
        try:
            proof = record_delivery_proof(actor=request.user, shipment_id=pk, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages)
        else:
            return redirect("proof_detail", pk=proof.pk)
    return render(request, "dashboard/workflow_form.html", {"title": "Delivery proof: " + shipment.tracking_number, "eyebrow": "Signed document or signature image · Evidence cannot be overwritten", "form": form, "back_url": "shipment_list", "multipart": True})


@staff_permission_required("operations.view_deliveryproof", "shipments.view_shipment")
@require_GET
def proof_detail(request, pk):
    proof = get_object_or_404(DeliveryProof.objects.defer("evidence").select_related("shipment", "recorded_by"), pk=pk)
    return detail(request, title="Delivery proof", back_url="shipment_list", fields=[
        ("Proof reference", proof.reference), ("Shipment", proof.shipment.tracking_number), ("Recipient", proof.recipient_name),
        ("Delivered at", proof.delivered_at), ("Notes", proof.notes), ("Recorded by", proof.recorded_by),
        ("Recorded at", proof.recorded_at), ("Evidence SHA-256", proof.evidence_sha256),
    ], actions=[action("shipment_detail", "View shipment", proof.shipment_id), action("proof_evidence", "Download signed evidence", pk)], proof=proof,
        audit=OperationsEvent.objects.filter(entity_type="proof", entity_id=str(pk)))


@staff_permission_required("operations.view_deliveryproof", "shipments.view_shipment")
@require_GET
def proof_evidence(request, pk):
    proof = get_object_or_404(DeliveryProof, pk=pk)
    record = event(request.user, "proof", pk, "evidence_downloaded", proof_reference=str(proof.reference))
    response = FileResponse(BytesIO(bytes(proof.evidence)), as_attachment=True, filename=proof.evidence_name, content_type=proof.evidence_type)
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "sandbox"
    response["X-Audit-Reference"] = str(record.reference)
    return response


@staff_permission_required("operations.view_deliveryproof", "shipments.view_shipment", "operations.export_reports")
@require_GET
@transaction.atomic
def proof_export(request, pk, format):
    if format not in {"csv", "pdf"}:
        raise Http404
    proof = get_object_or_404(DeliveryProof.objects.defer("evidence").select_related("shipment__quote", "recorded_by"), pk=pk)
    record = event(request.user, "proof", pk, "proof_exported", format=format, proof_reference=str(proof.reference))
    exporter = export_pdf if format == "pdf" else export_csv
    return exporter(title="Proof of delivery", columns=["Field", "Value"], rows=[
        ["Proof reference", proof.reference], ["Shipment", proof.shipment.tracking_number], ["Quotation", proof.shipment.quote.quote_number],
        ["Recipient", proof.recipient_name], ["Delivered", timezone.localtime(proof.delivered_at).isoformat(timespec="seconds")], ["Recorded", timezone.localtime(proof.recorded_at).isoformat(timespec="seconds")],
        ["Recorded by", proof.recorded_by or "Former staff"], ["Evidence SHA-256", proof.evidence_sha256],
    ], reference=record.reference, metadata=[("Notes", proof.notes or "None"), ("Evidence", "Original evidence is retained separately; use the authenticated evidence download.")], **({"portrait": True, "evidence_image": bytes(proof.evidence) if proof.evidence_type.startswith("image/") else None} if format == "pdf" else {}))


REPORTS = {
    "quotations": ("Quotations", "quotations.view_quote", Quote.STATUS_CHOICES),
    "shipments": ("Shipments", "shipments.view_shipment", Shipment.STATUS_CHOICES),
    "inventory": ("Inventory", "operations.view_inventoryitem", [("active", "Active"), ("archived", "Archived")]),
    "staff": ("Staff", "accounts.view_employeeprofile", EmployeeProfile.STATUS),
    "proofs": ("Delivery proofs", "operations.view_deliveryproof", [("delivered", "Delivered")]),
}


def report_query(kind, data):
    if kind == "quotations":
        queryset = search(Quote.objects.select_related("customer", "prepared_by"), data.get("q"), ("quote_number", "customer__full_name", "destination"))
        if data.get("staff"):
            queryset = queryset.filter(prepared_by=data["staff"])
        audit = AuditRecord.objects.filter(quote_id=OuterRef("pk"), shipment__isnull=True).order_by("-pk")
        queryset = queryset.annotate(audit_ref=Subquery(audit.values("pk")[:1]))
    elif kind == "shipments":
        queryset = search(Shipment.objects.select_related("quote__customer", "created_by"), data.get("q"), ("tracking_number", "quote__customer__full_name", "quote__destination"))
        if data.get("staff"):
            queryset = queryset.filter(created_by=data["staff"])
        audit = AuditRecord.objects.filter(shipment_id=OuterRef("pk")).order_by("-pk")
        queryset = queryset.annotate(audit_ref=Subquery(audit.values("pk")[:1]))
    elif kind == "inventory":
        queryset = search(InventoryItem.objects.select_related("warehouse"), data.get("q"), ("sku", "name", "warehouse__name"))
        if data.get("staff"):
            queryset = queryset.filter(movements__actor=data["staff"]).distinct()
        if data.get("status"):
            queryset = queryset.filter(is_active=data["status"] == "active")
    elif kind == "staff":
        queryset = search(EmployeeProfile.objects.select_related("user", "department"), data.get("q"), ("employee_id", "user__username", "user__first_name", "user__last_name"))
        if data.get("staff"):
            queryset = queryset.filter(user=data["staff"])
    else:
        queryset = search(DeliveryProof.objects.defer("evidence").select_related("shipment", "recorded_by"), data.get("q"), ("recipient_name", "shipment__tracking_number"))
        if data.get("staff"):
            queryset = queryset.filter(recorded_by=data["staff"])
    if data.get("status") and kind in {"quotations", "shipments", "staff"}:
        queryset = queryset.filter(status=data["status"])
    if kind in {"inventory", "staff", "proofs"}:
        entity = {"inventory": "inventory", "staff": "staff", "proofs": "proof"}[kind]
        from django.db.models.functions import Cast
        from django.db.models import CharField
        queryset = queryset.annotate(object_key=Cast("pk", output_field=CharField()))
        audit = OperationsEvent.objects.filter(entity_type=entity, entity_id=OuterRef("object_key")).order_by("-pk")
        queryset = queryset.annotate(audit_ref=Subquery(audit.values("reference")[:1]))
    return date_range(queryset, data, "recorded_at" if kind == "proofs" else "created_at").order_by("-recorded_at" if kind == "proofs" else "-created_at", "-pk")


def report_rows(kind, records):
    def timestamp(value):
        return timezone.localtime(value).strftime("%d %b %Y %H:%M:%S %Z")
    for obj in records:
        audit = ("AUD-" if kind in {"quotations", "shipments"} else "OPS-") + str(obj.audit_ref) if obj.audit_ref else "Legacy / no event"
        if kind == "quotations":
            values = [obj.quote_number, obj.customer.full_name, obj.status, obj.currency, obj.total_amount, obj.prepared_by or "Public / legacy", timestamp(obj.created_at), audit]
            url = reverse("quotation_detail", args=[obj.pk])
        elif kind == "shipments":
            values = [obj.tracking_number, obj.quote.customer.full_name, obj.status, obj.quote.destination, obj.created_by or "Legacy", timestamp(obj.created_at), audit]
            url = reverse("shipment_detail", args=[obj.pk])
        elif kind == "inventory":
            values = [obj.sku, obj.name, obj.warehouse.name, obj.quantity, obj.unit, "Active" if obj.is_active else "Archived", audit]
            url = reverse("inventory_detail", args=[obj.pk])
        elif kind == "staff":
            values = [obj.employee_id, obj.user.get_full_name() or obj.user.username, obj.department.name, obj.status, timestamp(obj.created_at), audit]
            url = reverse("staff_detail", args=[obj.pk])
        else:
            values = [obj.reference, obj.shipment.tracking_number, obj.recipient_name, timestamp(obj.delivered_at), obj.recorded_by or "Former staff", audit]
            url = reverse("proof_detail", args=[obj.pk])
        yield {"values": values, "url": url}


REPORT_COLUMNS = {
    "quotations": ["Quotation", "Customer", "Status", "Currency", "Total", "Preparer", "Created", "Audit"],
    "shipments": ["Tracking", "Customer", "Status", "Destination", "Booked by", "Created", "Audit"],
    "inventory": ["SKU", "Item", "Warehouse", "On hand", "Unit", "Status", "Audit"],
    "staff": ["Employee ID", "Name", "Department", "Status", "Created", "Audit"],
    "proofs": ["Proof reference", "Tracking", "Recipient", "Delivered", "Recorded by", "Audit"],
}


@staff_permission_required("operations.view_reports")
@require_GET
@transaction.atomic
def reports(request):
    available = [(key, spec[0]) for key, spec in REPORTS.items() if request.user.has_perm(spec[1]) and (key != "proofs" or request.user.has_perm("shipments.view_shipment"))]
    if not available:
        raise PermissionDenied
    kind = request.GET.get("report", available[0][0])
    if kind not in dict(available):
        raise PermissionDenied
    form = ReportFilterForm(request.GET, statuses=REPORTS[kind][2])
    valid = form.is_valid()
    queryset = report_query(kind, form.cleaned_data if valid else {})
    if not valid:
        queryset = queryset.none()
    format = request.GET.get("format")
    if format:
        if not request.user.has_perm("operations.export_reports"):
            raise PermissionDenied
        if format not in {"csv", "pdf"} or not valid:
            return HttpResponseBadRequest("Choose valid report filters and CSV or PDF format.")
        count = queryset.count()
        limit = 1000 if format == "pdf" else 10000
        if count > limit:
            return HttpResponseBadRequest(f"Export limit is {limit} records. Narrow the report filters.")
        filters = {key: str(value) for key, value in form.cleaned_data.items() if value is not None and value != ""}
        record = event(request.user, "report", kind, "report_exported", format=format, count=count, filters=filters)
        exporter = export_pdf if format == "pdf" else export_csv
        return exporter(title=REPORTS[kind][0] + " report", columns=REPORT_COLUMNS[kind], rows=(row["values"] for row in report_rows(kind, queryset.iterator(chunk_size=200))), reference=record.reference, metadata=[("Generated by", request.user.get_username()), ("Filters", "; ".join(f"{key}={value}" for key, value in filters.items()) or "All records")])
    page, paging = paginate(request, queryset)
    totals = queryset.values("currency").annotate(amount=Sum("total_amount")).order_by("currency") if kind == "quotations" else []
    return render(request, "operations/reports.html", {"title": "Operational reports", "report_kind": kind, "report_choices": available,
        "filter_form": form, "columns": REPORT_COLUMNS[kind], "rows": list(report_rows(kind, page)), "totals": totals,
        "can_export": request.user.has_perm("operations.export_reports"), **paging})
