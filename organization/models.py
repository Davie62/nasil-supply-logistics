from django.db import models

from core.models import BaseModel


class Company(BaseModel):
    """
    Company information.
    """

    name = models.CharField(max_length=200)

    registration_number = models.CharField(
        max_length=100,
        unique=True
    )

    tin = models.CharField(
        max_length=100,
        unique=True
    )

    email = models.EmailField()

    phone = models.CharField(max_length=30)

    website = models.URLField(
        blank=True
    )

    address = models.TextField()

    logo = models.ImageField(
        upload_to="company/",
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name


class Branch(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="branches"
    )

    name = models.CharField(max_length=150)

    code = models.CharField(
        max_length=20,
        unique=True
    )

    city = models.CharField(max_length=100)

    country = models.CharField(max_length=100)

    address = models.TextField()

    phone = models.CharField(max_length=30)

    email = models.EmailField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Department(BaseModel):

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="departments"
    )

    name = models.CharField(max_length=100)

    code = models.CharField(
        max_length=20,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Warehouse(BaseModel):

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="warehouses"
    )

    name = models.CharField(max_length=150)

    code = models.CharField(
        max_length=20,
        unique=True
    )

    location = models.TextField()

    capacity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    manager = models.CharField(
        max_length=150,
        blank=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
