from django.contrib import admin
from django.apps import apps
from customer_services.admin import ReadOnlyAdmin

for model in apps.get_app_config(__package__).get_models():
    if not admin.site.is_registered(model):
        admin.site.register(model, ReadOnlyAdmin)
