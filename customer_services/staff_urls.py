from django.urls import path
from . import staff_views

urlpatterns = [
    path("customers/<int:pk>/access/", staff_views.manage_access, name="customer_portal_access"),
    path("invoices/", staff_views.invoice_list, name="staff_invoice_list"),
    path("invoices/new/", staff_views.invoice_create, name="staff_invoice_create"),
    path("invoices/<int:pk>/", staff_views.invoice_detail, name="staff_invoice_detail"),
    path("invoices/<int:pk>/pdf/", staff_views.invoice_pdf, name="staff_invoice_pdf"),
]
