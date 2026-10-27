from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("quote/", views.quote, name="quote"),
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    path("services/manage/", views.service_list, name="service_list"),
    path("services/manage/new/", views.service_create, name="service_create"),
    path("services/manage/<int:pk>/edit/", views.service_update, name="service_update"),
    path("carriers/", views.carrier_list, name="carrier_list"),
    path("carriers/new/", views.carrier_create, name="carrier_create"),
    path("carriers/<int:pk>/edit/", views.carrier_update, name="carrier_update"),
]