from django.contrib.auth.models import AbstractUser
from django.db import models

from organization.models import Branch, Department


class User(AbstractUser):
    """
    Custom authentication model.
    """

    email = models.EmailField(unique=True)

    is_verified = models.BooleanField(default=False)

    last_password_change = models.DateTimeField(
        null=True,
        blank=True
    )

    failed_login_attempts = models.PositiveIntegerField(default=0)

    locked_until = models.DateTimeField(
        null=True,
        blank=True
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username


class EmployeeProfile(models.Model):

    STATUS = [
        ("ACTIVE", "Active"),
        ("SUSPENDED", "Suspended"),
        ("LEAVE", "On Leave"),
        ("TERMINATED", "Terminated"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    employee_id = models.CharField(
        max_length=30,
        unique=True,
        db_index=True
    )

    phone_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="employees"
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="employees"
    )

    position = models.CharField(
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

        indexes = [
            models.Index(fields=["employee_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        full_name = self.user.get_full_name() or self.user.username
        return f"{self.employee_id} - {full_name}"