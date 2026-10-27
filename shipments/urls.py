from django.urls import path

from . import views
from operations.views import shipment_detail

urlpatterns = [
    path("<int:pk>/", shipment_detail, name="shipment_detail"),
	path("", views.shipment_list, name="shipment_list"),
	path("new/", views.shipment_create, name="shipment_create"),
	path("<int:pk>/edit/", views.shipment_update, name="shipment_update"),
]
