from django.contrib import admin
from .models import Quote

@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('quote_number', 'customer', 'pickup_location', 'destination', 'status', 'created_at')
    search_fields = ('quote_number', 'customer__full_name', 'customer__email', 'pickup_location', 'destination')
    list_filter = ('status', 'created_at', 'service')
    ordering = ('-created_at',)
    readonly_fields = ('quote_number', 'created_at')
