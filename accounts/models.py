
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom User model for authentication.
    Additional authentication fields can be added here later
    (MFA, failed login attempts, account lockout, etc.)
    """

    email = models.EmailField(unique=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username


class EmployeeProfile(models.Model):

    DEPARTMENTS = [
        ("ADMIN", "Administration"),
        ("OPERATIONS", "Operations"),
        ("DISPATCH", "Dispatch"),
        ("WAREHOUSE", "Warehouse"),
        ("FINANCE", "Finance"),
        ("SALES", "Sales & Marketing"),
        ("HR", "Human Resources"),
        ("IT", "Information Technology"),
    ]

    STATUS = [
        ("ACTIVE", "Active"),
        ("SUSPENDED", "Suspended"),
        ("LEAVE", "On Leave"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    employee_id = models.CharField(
        max_length=20,
        unique=True
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True
    )

    department = models.CharField(
        max_length=20,
        choices=DEPARTMENTS
    )

    position = models.CharField(
        max_length=100
    )

    branch = models.CharField(
        max_length=100
    )

    profile_photo = models.ImageField(
        upload_to="employees/",
        blank=True,
        null=True
    )

    hire_date = models.DateField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="ACTIVE"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee_id"]

    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name()}"