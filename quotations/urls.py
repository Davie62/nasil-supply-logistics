from django.urls import path

from . import views
from operations.views import quotation_detail

urlpatterns = [
    path("<int:pk>/", quotation_detail, name="quotation_detail"),
	path("", views.quotation_list, name="quotation_list"),
	path("new/", views.quotation_create, name="quotation_create"),
	path("<int:pk>/edit/", views.quotation_update, name="quotation_update"),
]
