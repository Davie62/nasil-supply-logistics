from django.contrib import admin
from .models import OperationsEvent


@admin.register(OperationsEvent)
class OperationsEventAdmin(admin.ModelAdmin):
    list_display = ("reference", "created_at", "actor_label", "entity_type", "action")
    list_filter = ("entity_type", "action")
    search_fields = ("actor_label", "entity_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
