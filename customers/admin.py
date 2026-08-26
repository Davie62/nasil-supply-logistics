from django.contrib import admin
from .models import Customer

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company_name', 'email', 'phone', 'created_at')
    search_fields = ('full_name', 'company_name', 'email', 'phone')
    list_filter = ('created_at',)
    ordering = ('-created_at',)
