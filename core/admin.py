from django.contrib import admin
from .models import ContactMessage
from .models import AuditRecord


@admin.register(AuditRecord)
class AuditRecordAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'quote', 'shipment', 'actor_label', 'from_status', 'to_status')
    list_filter = ('action', 'to_status')
    search_fields = ('quote__quote_number', 'shipment__tracking_number', 'actor_label')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'is_read', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    list_filter = ('is_read', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
