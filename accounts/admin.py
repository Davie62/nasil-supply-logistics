from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, EmployeeProfile


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_verified",
        "is_active",
    )

    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
    )

    ordering = (
        "username",
    )

    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "is_verified",
    )

    fieldsets = UserAdmin.fieldsets + (
        (
            "Security",
            {
                "fields": (
                    "is_verified",
                    "failed_login_attempts",
                    "locked_until",
                    "last_password_change",
                )
            },
        ),
    )


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):

    list_display = (
        "employee_id",
        "user",
        "department",
        "branch",
        "position",
        "status",
    )

    search_fields = (
        "employee_id",
        "user__username",
        "user__first_name",
        "user__last_name",
    )

    list_filter = (
        "department",
        "branch",
        "status",
    )

    ordering = (
        "employee_id",
    )