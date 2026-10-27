from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .services import EmployeeService, OrganizationNotConfigured


@receiver(post_save, sender=User)
def create_employee(sender, instance, created, **kwargs):

    if not kwargs.get("raw") and instance.is_staff:

        try:
            EmployeeService.create_employee_profile(instance)

        except OrganizationNotConfigured:
            # Organization not configured yet.
            pass
