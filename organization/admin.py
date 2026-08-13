
from django.contrib import admin

from .models import Company, Branch, Department, Warehouse


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "registration_number",
        "email",
        "phone",
        "is_active",
    )

    search_fields = (
        "name",
        "registration_number",
        "email",
    )

    list_filter = (
        "is_active",
    )

    ordering = (
        "name",
    )


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "code",
        "city",
        "country",
        "is_active",
    )

    search_fields = (
        "name",
        "code",
        "city",
    )

    list_filter = (
        "country",
        "is_active",
    )

    ordering = (
        "name",
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "branch",
        "code",
        "is_active",
    )

    search_fields = (
        "name",
        "code",
    )

    list_filter = (
        "branch",
        "is_active",
    )

    ordering = (
        "name",
    )


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "branch",
        "code",
        "capacity",
        "is_active",
    )

    search_fields = (
        "name",
        "code",
    )

    list_filter = (
        "branch",
        "is_active",
    )

    ordering = (
        "name",
    )