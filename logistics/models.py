from django.db import models

class Service(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField()
    icon = models.CharField(max_length=50, blank=True, null=True, help_text="CSS class for icon (e.g., 'bi bi-truck')")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Carrier(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
