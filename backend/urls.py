"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("integrations/", include("integrations.urls")),
    path("finance/", include("finance.urls")),
    path("inventory/", include("inventory.urls")),
    path("orders/", include("orders.urls")),
    path("procurement/", include("procurement.urls")),
    path("fleet/", include("fleet.urls")),
    path("portal/", include("customer_services.urls")),
    path("customer-services/", include("customer_services.staff_urls")),
    path("admin/", admin.site.urls),

    # Main website
    path("", include("logistics.urls")),

    # Authentication
    path("accounts/", include("accounts.urls")),

    # Dashboard
    path("dashboard/", include("dashboard.urls")),

    # Shipments
    path("shipments/", include("shipments.urls")),

    # Quotations
    path("quotations/", include("quotations.urls")),

    # Payments
    path("payments/", include("payments.urls")),
    path("customers/", include("customers.urls")),
    path("messages/", include("core.urls")),
    path("operations/", include("operations.urls")),
]

from customer_services.views import public_tracking
urlpatterns += [path("track/", public_tracking, name="public_tracking"), path("track/<str:tracking_number>/", public_tracking, name="public_tracking_result")]
