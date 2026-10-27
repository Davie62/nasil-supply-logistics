from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.constants import COMPANY_PREFIX
from organization.models import Department
from .models import EmployeeIDSequence, EmployeeProfile


class OrganizationNotConfigured(ValueError):
    pass


class EmployeeService:
    @staticmethod
    @transaction.atomic
    def generate_employee_id():
        year = timezone.localdate().year
        sequence, _ = EmployeeIDSequence.objects.get_or_create(year=year)
        # UPDATE serializes concurrent allocations on PostgreSQL until commit.
        EmployeeIDSequence.objects.filter(pk=year).update(last_number=F("last_number") + 1)
        sequence.refresh_from_db()
        return f"{COMPANY_PREFIX}-{year}-{sequence.last_number:05d}"

    @staticmethod
    @transaction.atomic
    def create_employee_profile(user):
        department = Department.objects.select_related("branch").filter(
            branch__is_active=True, branch__is_deleted=False,
        ).first()
        if department is None:
            raise OrganizationNotConfigured("Create an active branch and department first.")
        type(user).objects.select_for_update().get(pk=user.pk)
        profile = EmployeeProfile.objects.filter(user=user).first()
        if profile is not None:
            return profile
        return EmployeeProfile.objects.create(
            user=user,
            employee_id=EmployeeService.generate_employee_id(),
            branch=department.branch,
            department=department,
            position="Employee",
        )
