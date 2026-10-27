from django.contrib import admin
from .models import CustomerAccess, CustomerNotification, DeliveryAttempt, PortalInvitation


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerNotification)
class NotificationAdmin(ReadOnlyAdmin):
    list_display = ("reference", "customer", "kind", "channel", "status", "attempts", "provider", "created_at")
    list_filter = ("status", "channel", "kind", "provider")
    exclude = ("payload", "lease_token")


admin.site.register(CustomerAccess, ReadOnlyAdmin)
admin.site.register(PortalInvitation, ReadOnlyAdmin)
admin.site.register(DeliveryAttempt, ReadOnlyAdmin)
