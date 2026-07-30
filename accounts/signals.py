from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, EmployeeProfile


@receiver(post_save, sender=User)
def create_employee_profile(sender, instance, created, **kwargs):
    if created:
        EmployeeProfile.objects.create(
            user=instance,
            employee_id=f"NSL-{instance.id:04d}",
            department="ADMIN",
            position="Employee",
            branch="Head Office",
        )


@receiver(post_save, sender=User)
def save_employee_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()