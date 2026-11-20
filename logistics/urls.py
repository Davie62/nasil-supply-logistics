from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("industries/", views.industries, name="industries"),
    path("coverage/", views.coverage, name="coverage"),
    path("quote/", views.quote, name="quote"),
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("cookies/", views.cookies, name="cookies"),
    path("services/manage/", views.service_list, name="service_list"),
    path("services/manage/new/", views.service_create, name="service_create"),
    path("services/manage/<int:pk>/edit/", views.service_update, name="service_update"),
    path("carriers/", views.carrier_list, name="carrier_list"),
    path("carriers/new/", views.carrier_create, name="carrier_create"),
    path("carriers/<int:pk>/edit/", views.carrier_update, name="carrier_update"),
]