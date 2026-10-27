from django.contrib import messages
from core.permissions import staff_permission_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CustomerForm
from .models import Customer
from operations.querysets import paginate, search
from django.urls import reverse


@staff_permission_required("customers.view_customer")
def customer_list(request):
	customers = Customer.objects.order_by("full_name")
	customers = search(customers, request.GET.get("q"), ("full_name", "company_name", "email", "phone"))
	page, pagination = paginate(request, customers)
	rows = [
		{
			"values": [customer.full_name, customer.company_name or "-", customer.email, customer.phone],
			"url": reverse("customer_portal_access", args=[customer.pk]) if request.user.has_perm("customer_services.manage_access") else (f"/customers/{customer.pk}/edit/" if request.user.has_perm("customers.change_customer") else ""),
			"action_url": reverse("customer_portal_access", args=[customer.pk]) if request.user.has_perm("customer_services.manage_access") else "",
			"action_label": "Portal access",
		}
		for customer in page
	]
	return render(request, "dashboard/workflow_list.html", {
		"title": "Customers",
		**pagination,
		"eyebrow": "CUSTOMER MANAGEMENT",
		"description": "Maintain customer contacts used by quotations and shipments.",
		"columns": ["Name", "Company", "Email", "Phone"],
		"rows": rows,
		"row_actions": request.user.has_perm("customer_services.manage_access"),
		"create_url": "customer_create" if request.user.has_perm("customers.add_customer") else None,
		"create_label": "Add customer",
	})


@staff_permission_required("customers.view_customer", "customers.add_customer")
def customer_create(request):
	form = CustomerForm(request.POST or None)
	if form.is_valid():
		form.save()
		messages.success(request, "Customer created successfully.")
		return redirect("customer_list")
	return render(request, "dashboard/workflow_form.html", {
		"title": "Add customer",
		"eyebrow": "CUSTOMER MANAGEMENT",
		"form": form,
		"back_url": "customer_list",
	})


@staff_permission_required("customers.view_customer", "customers.change_customer")
def customer_update(request, pk):
	customer = get_object_or_404(Customer, pk=pk)
	form = CustomerForm(request.POST or None, instance=customer)
	if form.is_valid():
		form.save()
		messages.success(request, "Customer updated successfully.")
		return redirect("customer_list")
	return render(request, "dashboard/workflow_form.html", {
		"title": "Edit customer",
		"eyebrow": "CUSTOMER MANAGEMENT",
		"form": form,
		"back_url": "customer_list",
	})
from django.shortcuts import render

# Create your views here.
