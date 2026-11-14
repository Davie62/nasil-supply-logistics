from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("shipments/", views.module_placeholder, {"module": "shipments"}, name="dashboard_shipments"),
    path("quotations/", views.module_placeholder, {"module": "quotations"}, name="dashboard_quotations"),
    path("employees/", views.module_placeholder, {"module": "employees"}, name="dashboard_employees"),
    path("reports/", views.module_placeholder, {"module": "reports"}, name="dashboard_reports"),
    path("settings/", views.module_placeholder, {"module": "settings"}, name="dashboard_settings"),
]