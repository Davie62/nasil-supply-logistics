from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from core.forms import ContactMessageForm
from customers.models import Customer
from quotations.forms import PublicQuoteForm
from .forms import CarrierForm, ServiceForm
from .models import Carrier, Service

from core.permissions import staff_permission_required
from django.db import transaction
from django.views.decorators.http import require_http_methods
from operations.querysets import paginate, search


def home(request):
    return render(request, "home.html")


def about(request):
    return render(request, "about.html")


def services(request):
    return render(request, "services.html")


@require_http_methods(["GET", "POST"])
def quote(request):
    form = PublicQuoteForm(request.POST if request.method == "POST" else None,
                           initial={"email": request.GET.get("fq_email", "")})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            customer, _ = Customer.objects.get_or_create(
                email=form.cleaned_data["email"],
                defaults={key: form.cleaned_data[key]
                          for key in ("full_name", "company_name", "phone")},
            )
            quotation = form.save(commit=False)
            quotation.customer = customer
            quotation.save()
        messages.success(request, f"Quote request (Ref: {quotation.quote_number}) submitted successfully. We will get back to you shortly.")
        return redirect("quote")
    return render(request, "quote.html", {"form": form})


@require_http_methods(["GET", "POST"])
def contact(request):
    data = request.POST.copy() if request.method == "POST" else None
    if data is not None:
        data["name"] = " ".join(filter(None, (
            data.get("name", "").strip(), data.get("lastname", "").strip(),
        )))
    form = ContactMessageForm(data)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thank you for reaching out! Your message has been sent successfully.")
        return redirect("contact")
    return render(request, "contact.html", {"form": form})

def faq(request):
    return render(request, "faq.html")


@staff_permission_required("logistics.view_service")
def service_list(request):
    services = Service.objects.order_by("name")
    page, pagination = paginate(request, search(services, request.GET.get("q"), ("name", "description")))
    rows = [{
        "values": [service.name, service.description, "Active" if service.is_active else "Inactive"],
        "url": f"/services/manage/{service.pk}/edit/" if request.user.has_perm("logistics.change_service") else "",
    } for service in page]
    return render(request, "dashboard/workflow_list.html", {
        "title": "Services", "eyebrow": "SERVICE MANAGEMENT",
        **pagination,
        "description": "Maintain the services available for quotation requests.",
        "columns": ["Name", "Description", "Status"], "rows": rows, "status_column": 2,
        "create_url": "service_create" if request.user.has_perm("logistics.add_service") else None, "create_label": "Add service",
    })


@staff_permission_required("logistics.view_service", "logistics.add_service")
def service_create(request):
    form = ServiceForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Service created successfully.")
        return redirect("service_list")
    return render(request, "dashboard/workflow_form.html", {"title": "Add service", "eyebrow": "SERVICE MANAGEMENT", "form": form, "back_url": "service_list"})


@staff_permission_required("logistics.view_service", "logistics.change_service")
def service_update(request, pk):
    service = get_object_or_404(Service, pk=pk)
    form = ServiceForm(request.POST or None, instance=service)
    if form.is_valid():
        form.save()
        messages.success(request, "Service updated successfully.")
        return redirect("service_list")
    return render(request, "dashboard/workflow_form.html", {"title": "Edit service", "eyebrow": "SERVICE MANAGEMENT", "form": form, "back_url": "service_list"})


@staff_permission_required("logistics.view_carrier")
def carrier_list(request):
    carriers = Carrier.objects.order_by("name")
    page, pagination = paginate(request, search(carriers, request.GET.get("q"), ("name", "contact_person", "phone")))
    rows = [{
        "values": [carrier.name, carrier.contact_person or "-", carrier.phone, "Active" if carrier.is_active else "Inactive"],
        "url": f"/carriers/{carrier.pk}/edit/" if request.user.has_perm("logistics.change_carrier") else "",
    } for carrier in page]
    return render(request, "dashboard/workflow_list.html", {
        "title": "Carriers", "eyebrow": "OPERATIONS",
        **pagination,
        "description": "Maintain the logistics partners assigned to shipments.",
        "columns": ["Name", "Contact", "Phone", "Status"], "rows": rows, "status_column": 3,
        "create_url": "carrier_create" if request.user.has_perm("logistics.add_carrier") else None, "create_label": "Add carrier",
    })


@staff_permission_required("logistics.view_carrier", "logistics.add_carrier")
def carrier_create(request):
    form = CarrierForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Carrier created successfully.")
        return redirect("carrier_list")
    return render(request, "dashboard/workflow_form.html", {"title": "Add carrier", "eyebrow": "OPERATIONS", "form": form, "back_url": "carrier_list"})


@staff_permission_required("logistics.view_carrier", "logistics.change_carrier")
def carrier_update(request, pk):
    carrier = get_object_or_404(Carrier, pk=pk)
    form = CarrierForm(request.POST or None, instance=carrier)
    if form.is_valid():
        form.save()
        messages.success(request, "Carrier updated successfully.")
        return redirect("carrier_list")
    return render(request, "dashboard/workflow_form.html", {"title": "Edit carrier", "eyebrow": "OPERATIONS", "form": form, "back_url": "carrier_list"})
