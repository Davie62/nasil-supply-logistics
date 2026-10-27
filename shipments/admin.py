from django.contrib import admin
from .models import Shipment

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'quote', 'carrier', 'status', 'estimated_delivery', 'created_at')
    search_fields = ('tracking_number', 'quote__quote_number', 'carrier__name')
    list_filter = ('status', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('tracking_number', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
