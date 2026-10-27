from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import TemplateView
from . import views
from . import registration_views

urlpatterns = [
    path("", views.dashboard, name="portal_dashboard"),
    path("login/", views.portal_login, name="portal_login"),
    path("register/", registration_views.register, name="portal_register"),
    path("verify-email/", registration_views.verify_email, name="portal_verify_email"),
    path("logout/", views.portal_logout, name="portal_logout"),
    path("activate/<str:token>/", views.activate, name="portal_activate"),
    path("quotations/", views.quotation_list, name="portal_quotes"),
    path("quotations/<int:pk>/", views.quotation_detail, name="portal_quote"),
    path("shipments/", views.shipment_list, name="portal_shipments"),
    path("shipments/<int:pk>/", views.shipment_detail, name="portal_shipment"),
    path("proofs/<int:pk>/evidence/", views.evidence, name="portal_evidence"),
    path("invoices/", views.invoice_list, name="portal_invoices"),
    path("invoices/<int:pk>/", views.invoice_detail, name="portal_invoice"),
    path("invoices/<int:pk>/pdf/", views.invoice_pdf, name="portal_invoice_pdf"),
    path("notifications/", views.notifications, name="portal_notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="portal_notification_read"),
    path("preferences/", views.preferences, name="portal_preferences"),
    path("password-reset/", views.ResetRequestView.as_view(), name="portal_password_reset"),
    path("password-reset/sent/", TemplateView.as_view(template_name="portal/reset_message.html", extra_context={"title": "Check your email", "message": "If an eligible customer account exists, a recovery email has been queued."}), name="portal_reset_sent"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="portal/auth.html", success_url=reverse_lazy("portal_reset_complete"), extra_context={"title": "Choose a new password"}), name="portal_reset_confirm"),
    path("reset/complete/", TemplateView.as_view(template_name="portal/reset_message.html", extra_context={"title": "Password updated", "message": "You can now sign in with your new password."}), name="portal_reset_complete"),
]
