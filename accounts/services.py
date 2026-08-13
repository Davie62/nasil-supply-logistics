from datetime import datetime
from django.db import transaction
from core.constants import COMPANY_PREFIX

from .models import User, EmployeeProfile
from organization.models import Branch, Department


class EmployeeService:
    """
    Handles all employee-related business logic.
    """

    @staticmethod
    def generate_employee_id():
        """
        Generates IDs like:

        NSL-2026-00001
        """

        year = datetime.now().year

        last_employee = (
            EmployeeProfile.objects
            .order_by("-created_at")
            .first()
        )

        if last_employee:
            try:
                last_number = int(
                    last_employee.employee_id.split("-")[-1]
                )
            except Exception:
                last_number = 0
        else:
            last_number = 0

        
            return f"{COMPANY_PREFIX}-{year}-{last_number + 1:05d}"

    @staticmethod
    @transaction.atomic
    def create_employee_profile(user):

        branch = Branch.objects.first()
        department = Department.objects.first()

        if not branch:
            raise ValueError(
                "No Branch exists."
            )

        if not department:
            raise ValueError(
                "No Department exists."
            )

        return EmployeeProfile.objects.create(
            user=user,
            employee_id=EmployeeService.generate_employee_id(),
            branch=branch,
            department=department,
            position="Employee",
        )