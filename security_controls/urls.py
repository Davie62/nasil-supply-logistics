from django.urls import path
from . import views

urlpatterns = [
    path("account/", views.account_security, name="security_account"),
    path("mfa/setup/", views.setup, name="security_mfa_setup"),
    path("mfa/verify/", views.challenge, name="security_mfa_challenge"),
    path("mfa/qr/", views.qr, name="security_mfa_qr"),
    path("mfa/recovery/", views.recovery, name="security_mfa_recovery"),
]
