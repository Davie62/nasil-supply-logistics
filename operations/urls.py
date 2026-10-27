from django.urls import path
from . import views

urlpatterns = [
    path("inventory/", views.inventory_list, name="inventory_list"),
    path("inventory/new/", views.inventory_edit, name="inventory_create"),
    path("inventory/<int:pk>/", views.inventory_detail, name="inventory_detail"),
    path("inventory/<int:pk>/edit/", views.inventory_edit, name="inventory_update"),
    path("inventory/<int:pk>/move/", views.inventory_move, name="inventory_move"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/new/", views.staff_edit, name="staff_create"),
    path("staff/<int:pk>/", views.staff_detail, name="staff_detail"),
    path("staff/<int:pk>/edit/", views.staff_edit, name="staff_update"),
    path("staff/<int:pk>/deactivate/", views.staff_deactivate, name="staff_delete"),
    path("settings/", views.settings_view, name="operations_settings"),
    path("reports/", views.reports, name="operations_reports"),
    path("shipments/<int:pk>/proof/new/", views.proof_create, name="proof_create"),
    path("proofs/<int:pk>/", views.proof_detail, name="proof_detail"),
    path("proofs/<int:pk>/evidence/", views.proof_evidence, name="proof_evidence"),
    path("proofs/<int:pk>/export/<str:format>/", views.proof_export, name="proof_export"),
]
