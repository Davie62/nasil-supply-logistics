from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    return render(request, "dashboard/dashboard.html")


@login_required
def module_placeholder(request, module):
    modules = {
        "shipments": {"title": "Shipments", "eyebrow": "OPERATIONS", "description": "Track consignments, delivery progress, and shipment records from one workspace.", "icon": "bi-truck", "status": "Shipment workflows are being prepared."},
        "quotations": {"title": "Quotations", "eyebrow": "COMMERCIAL", "description": "Prepare, review, and manage customer quotations when the workflow is enabled.", "icon": "bi-file-earmark-text", "status": "Quotation workflows are being prepared."},
        "employees": {"title": "Employees", "eyebrow": "PEOPLE", "description": "Manage employee profiles, branches, departments, and operational access.", "icon": "bi-people", "status": "Employee management is being prepared."},
        "reports": {"title": "Reports", "eyebrow": "INSIGHTS", "description": "Review operational and commercial performance as reporting data becomes available.", "icon": "bi-bar-chart-line", "status": "Reporting tools are being prepared."},
        "settings": {"title": "Settings", "eyebrow": "ADMINISTRATION", "description": "Configure organization preferences and workspace behavior.", "icon": "bi-gear", "status": "Settings management is being prepared."},
    }
    context = modules.get(module)
    if context is None:
        from django.http import Http404
        raise Http404
    return render(request, "dashboard/module_placeholder.html", context)