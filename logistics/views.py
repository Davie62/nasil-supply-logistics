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


QUOTE_SERVICE_CONTEXTS = {
    "procurement": {
        "key": "procurement",
        "label": "Procurement & Sourcing",
        "intro": "Tell us what you need sourced or procured, including specifications, quantities, and delivery requirements.",
        "placeholders": {
            "pickup_location": "Supplier/source location (if known)",
            "destination": "Delivery location",
            "transport_mode": "Preferred transport mode (if applicable)",
            "cargo_description": "Describe items, specifications, quantities, and sourcing requirements",
            "special_instructions": "Timeline, preferred brands/quality, budget considerations, or other notes",
        },
        "service_terms": ["procure", "sourcing", "procurement"],
    },
    "supply": {
        "key": "supply",
        "label": "Supply Solutions",
        "intro": "Share details about the materials or products you need supplied for your operations or projects.",
        "placeholders": {
            "pickup_location": "Pickup/source location (if applicable)",
            "destination": "Delivery or site location",
            "transport_mode": "Preferred transport mode (if applicable)",
            "cargo_description": "Describe products/materials, specifications, and quantities needed",
            "special_instructions": "Project/site requirements, delivery schedule, handling needs, or other notes",
        },
        "service_terms": ["supply"],
    },
    "warehousing": {
        "key": "warehousing",
        "label": "Warehousing & Storage",
        "intro": "Tell us about the goods you need to store, including volume, duration, and any handling requirements.",
        "placeholders": {
            "pickup_location": "Current location / pickup point",
            "destination": "Storage/warehouse location or delivery destination",
            "transport_mode": "Inbound/outbound transport needs (if applicable)",
            "cargo_description": "Describe goods, quantity/volume, packaging, and storage needs",
            "special_instructions": "Storage duration, handling conditions, access/delivery schedule, or other notes",
        },
        "service_terms": ["warehous", "storage"],
    },
    "transport": {
        "key": "transport",
        "label": "Transport & Distribution",
        "intro": "Provide your pickup and destination details, schedule, and cargo information so we can plan transport and distribution.",
        "placeholders": {
            "pickup_location": "Pickup location",
            "destination": "Destination / delivery location(s)",
            "transport_mode": "Preferred mode (e.g. road, air, sea) if known",
            "cargo_description": "Describe goods, packaging, and quantity",
            "special_instructions": "Preferred schedule, handling requirements, distribution notes, or other details",
        },
        "service_terms": ["transport", "distribution", "shipping", "delivery"],
    },
    "import-export": {
        "key": "import-export",
        "label": "Import & Export Support",
        "intro": "Share origin and destination countries, goods details, and timelines so we can support your import or export requirements.",
        "placeholders": {
            "pickup_location": "Origin / pickup location (city, country)",
            "destination": "Destination (city, country)",
            "transport_mode": "Preferred mode (air, sea, road) if known",
            "cargo_description": "Describe goods, quantities, and any relevant specifications",
            "special_instructions": "Shipment timeline, Incoterms (if known), documentation/customs considerations, or other notes",
        },
        "service_terms": ["import", "export", "customs"],
    },
    "custom": {
        "key": "custom",
        "label": "Tailored Logistics Coordination",
        "intro": "Describe your specialized or multi-step requirements so we can coordinate the right supply and logistics solution.",
        "placeholders": {
            "pickup_location": "Origin / pickup location (if applicable)",
            "destination": "Destination / delivery location",
            "transport_mode": "Preferred mode(s) or handling needs (if known)",
            "cargo_description": "Describe your requirements, goods/materials, and scope",
            "special_instructions": "Timeline, special handling, coordination needs, or other details",
        },
        "service_terms": ["custom", "logistics", "coordination"],
    },
}


@require_http_methods(["GET", "POST"])
def quote(request):
    service_key = (request.POST.get("service") or request.GET.get("service") or "").strip().lower()
    selected_service = QUOTE_SERVICE_CONTEXTS.get(service_key)

    initial = {"email": request.GET.get("fq_email", "")}
    form = PublicQuoteForm(request.POST if request.method == "POST" else None, initial=initial)

    if selected_service:
        for field_name, placeholder in selected_service.get("placeholders", {}).items():
            if field_name in form.fields:
                form.fields[field_name].widget.attrs["placeholder"] = placeholder

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            customer, _ = Customer.objects.get_or_create(
                email=form.cleaned_data["email"],
                defaults={key: form.cleaned_data[key]
                          for key in ("full_name", "company_name", "phone")},
            )
            quotation = form.save(commit=False)
            quotation.customer = customer
            if selected_service:
                matched_service = None
                for term in selected_service.get("service_terms", []):
                    matched_service = Service.objects.filter(is_active=True, name__icontains=term).first()
                    if matched_service:
                        break
                quotation.service = matched_service
            quotation.save()
        messages.success(request, f"Quote request (Ref: {quotation.quote_number}) submitted successfully. We will get back to you shortly.")
        return redirect("quote")

    return render(request, "quote.html", {"form": form, "selected_service": selected_service})


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


def industries(request):
    return render(request, "industries.html")


def coverage(request):
    return render(request, "coverage.html")


def privacy(request):
    return render(request, "privacy.html")


def terms(request):
    return render(request, "terms.html")


def cookies(request):
    return render(request, "cookies.html")


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
