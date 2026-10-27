from django.urls import path

from . import views


urlpatterns = [
    path("", views.contact_message_list, name="contact_message_list"),
    path("<int:pk>/read/", views.contact_message_read, name="contact_message_read"),
]
