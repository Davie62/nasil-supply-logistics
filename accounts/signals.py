from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .services import EmployeeService


@receiver(post_save, sender=User)
def create_employee(sender, instance, created, **kwargs):

    if created:

        try:
            EmployeeService.create_employee_profile(instance)

        except ValueError:
            # Organization not configured yet.
            pass