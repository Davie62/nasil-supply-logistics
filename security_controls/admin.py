from django.contrib import admin
from .models import SecurityEvent, SecurityAlert


class ReadOnlySecurityAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SecurityEvent)
class SecurityEventAdmin(ReadOnlySecurityAdmin):
    list_display = ("created_at", "code", "level", "actor_id", "route", "reference")
    list_filter = ("code", "level")
    search_fields = ("request_id", "reference")
    list_select_related = ("actor",)


@admin.register(SecurityAlert)
class SecurityAlertAdmin(ReadOnlySecurityAdmin):
    list_display = ("created_at", "code", "event")
    list_filter = ("code",)
