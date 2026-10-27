"""Permission-checked, QuerySet-backed screens reused by separate commercial apps."""
from dataclasses import dataclass
from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from core.business_rules import require_permission
from .forms import StyledFormMixin
from .models import OperationsEvent
from .querysets import search, paginate, date_range
from .services import event
from .exports import export_csv, export_pdf


class ResourceForm(StyledFormMixin, forms.ModelForm):
    expected_version = forms.CharField(required=False, widget=forms.HiddenInput)


class ActionForm(StyledFormMixin, forms.Form):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


class ReasonForm(ActionForm):
    reason = forms.CharField(max_length=255)


class EmptyActionForm(ActionForm):
    pass


class FilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(max_length=150, required=False, label="Search")
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.CharField(max_length=30, required=False)
    staff = forms.IntegerField(required=False, min_value=1, label="Staff ID")

    def clean(self):
        values = super().clean()
        if values.get("date_from") and values.get("date_to") and values["date_from"] > values["date_to"]:
            raise forms.ValidationError("Start date must be before the end date.")
        return values


@dataclass
class Action:
    label: str
    permission: str
    form: object
    service: object


def display(obj, field):
    value = getattr(obj, field)
    return value() if callable(value) else value


def resource_urls(*, model, slug, form_class=None, save=None, columns, fields, search_fields=(), actions=None, related=None, select=(), queryset=None, entity=None):
    app = model._meta.app_label
    title = model._meta.verbose_name_plural.title()
    prefix = f"{app}:{slug}"
    permission = f"{app}.view_{model._meta.model_name}"
    entity = entity or model._meta.model_name
    actions = actions or {}

    def query():
        records = (queryset() if queryset else model.objects.all()).select_related(*select)
        return records if records.ordered else records.order_by("-pk")

    @login_required
    @require_GET
    def listing(request):
        require_permission(request.user, permission)
        filters = FilterForm(request.GET)
        records = query()
        if model._meta.label_lower == "inventory.stocklevel" and request.GET.get("low") == "1":
            records = records.filter(item__quantity__lte=F("item__reorder_level"))
        if filters.is_valid():
            data = filters.cleaned_data
            records = search(records, data.get("q"), search_fields)
            model_fields = {field.name for field in model._meta.fields}
            if "paid_at" in model_fields:
                records = date_range(records, data, field="paid_at")
            elif "statement_date" in model_fields:
                records = date_range(records, data, field="statement_date")
            elif "created_at" in model_fields:
                records = date_range(records, data)
            elif "issued_at" in model_fields:
                records = date_range(records, data, field="issued_at")
            if data.get("status") and "status" in model_fields:
                records = records.filter(status=data["status"])
            actor_field = next((field for field in ("recorded_by", "created_by", "assigned_by", "audited_by") if field in model_fields), None)
            if data.get("staff") and actor_field:
                records = records.filter(**{actor_field + "_id": data["staff"]})
        else:
            records = records.none()
        export = request.GET.get("format")
        if export in {"csv", "pdf"}:
            require_permission(request.user, "operations.export_reports")
            if not filters.is_valid():
                from django.http import HttpResponseBadRequest
                return HttpResponseBadRequest("Correct report filters before exporting.")
            limit = 10000 if export == "csv" else 1000
            if records.count() > limit:
                messages.error(request, f"Narrow the report to {limit:,} records or fewer.")
                return redirect(prefix + "_list")
            audit = event(request.user, entity, "report", "report_exported", format=export)
            utility = export_csv if export == "csv" else export_pdf
            return utility(title=title, columns=columns, rows=[[display(obj, field) for field in fields] for obj in records], reference=audit.reference)
        page, paging = paginate(request, records)
        return render(request, "expansion/list.html", {"title": title, "filter_form": filters, "columns": columns,
            "rows": [{"values": [display(obj, field) for field in fields], "url": reverse(prefix + "_detail", args=[obj.pk])} for obj in page],
            "create_url": prefix + "_create" if save and request.user.has_perm(f"{app}.add_{model._meta.model_name}") else None,
            "create_label": "Add " + model._meta.verbose_name, "can_export": request.user.has_perm("operations.export_reports"), **paging})

    def render_detail(request, obj, bound_action=None):
        action_forms = []
        for name, action in actions.items():
            if request.user.has_perm(action.permission):
                form = bound_action[1] if bound_action and bound_action[0] == name else action.form(obj)(initial={"expected_version": obj.version})
                action_forms.append({"label": action.label, "form": form, "url": reverse(prefix + "_action", args=[obj.pk, name])})
        audit, paging = paginate(request, OperationsEvent.objects.filter(entity_type=entity, entity_id=str(obj.pk)))
        return render(request, "expansion/detail.html", {"title": str(obj), "back_url": prefix + "_list",
            "fields": list(zip(columns, [display(obj, field) for field in fields])), "action_forms": action_forms,
            "edit_url": reverse(prefix + "_edit", args=[obj.pk]) if save and request.user.has_perm(f"{app}.change_{model._meta.model_name}") else None,
            "panels": related(obj) if related else [], "audit_records": audit, **paging})

    @login_required
    @require_GET
    def detail(request, pk):
        require_permission(request.user, permission)
        return render_detail(request, get_object_or_404(query(), pk=pk))

    @login_required
    @require_http_methods(["GET", "POST"])
    def editing(request, pk=None):
        require_permission(request.user, permission, f"{app}.{'change' if pk else 'add'}_{model._meta.model_name}")
        obj = get_object_or_404(query(), pk=pk) if pk else None
        initial = {"expected_version": getattr(obj, "version", str(obj.updated_at) if obj else "")} if obj else {}
        form = form_class(request.POST if request.method == "POST" else None, instance=obj, initial=initial)
        if form.is_valid():
            data = dict(form.cleaned_data)
            version = data.pop("expected_version", None) or None
            if obj and (version is None or version == ""):
                form.add_error(None, "Reload this record before saving.")
            else:
                try:
                    result = save(actor=request.user, record_id=pk, expected_version=int(version) if obj and hasattr(obj, "version") else version, data=data)
                except (ValidationError, IntegrityError, ValueError) as error:
                    form.add_error(None, error.messages if isinstance(error, ValidationError) else "Conflicting or invalid record. Reload and check unique references.")
                else:
                    return redirect(prefix + "_detail", pk=result.pk)
        return render(request, "dashboard/workflow_form.html", {"title": ("Edit " if pk else "Add ") + model._meta.verbose_name, "eyebrow": app.upper(), "form": form, "back_url": prefix + "_list"})

    @login_required
    @require_POST
    def action_view(request, pk, action_name):
        from django.http import Http404
        action = actions.get(action_name)
        if not action:
            raise Http404
        require_permission(request.user, permission, action.permission)
        obj = get_object_or_404(query(), pk=pk)
        form = action.form(obj)(request.POST)
        if form.is_valid():
            try:
                action.service(actor=request.user, record_id=obj.pk, **form.cleaned_data)
            except (ValidationError, IntegrityError) as error:
                form.add_error(None, error.messages if isinstance(error, ValidationError) else "Conflicting record or reference; reload before retrying.")
            else:
                messages.success(request, action.label + " completed.")
                return redirect(prefix + "_detail", pk=pk)
        return render_detail(request, obj, (action_name, form))

    converter = "uuid" if model._meta.pk.get_internal_type() == "UUIDField" else "int"
    patterns = [path(f"{slug}/", listing, name=slug + "_list"), path(f"{slug}/<{converter}:pk>/", detail, name=slug + "_detail"), path(f"{slug}/<{converter}:pk>/actions/<slug:action_name>/", action_view, name=slug + "_action")]
    if save:
        patterns.insert(0, path(f"{slug}/new/", editing, name=slug + "_create"))
        patterns.append(path(f"{slug}/<{converter}:pk>/edit/", editing, name=slug + "_edit"))
    return patterns


def home_view(title, links, metrics):
    @login_required
    @require_GET
    def home(request):
        available = [(label, url) for label, url, permission in links if request.user.has_perm(permission)]
        require_permission(request.user, *( [links[0][2]] if not available else []))
        return render(request, "expansion/home.html", {"title": title, "links": available, "metrics": metrics(request) if all(request.user.has_perm(permission) for _, _, permission in links) else []})
    return home
