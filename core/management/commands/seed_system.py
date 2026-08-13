from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

from organization.models import (
    Company,
    Branch,
    Department,
    Warehouse,
)


class Command(BaseCommand):
    help = "Seeds the system with default organization data."

    def handle(self, *args, **options):

        self.stdout.write(self.style.SUCCESS("\nSeeding NASIL System...\n"))

        # ------------------------------------------------------------------
        # COMPANY
        # ------------------------------------------------------------------

        company, _ = Company.objects.get_or_create(
            registration_number="800200000001",
            defaults={
                "name": "NASIL Supply & Logistics",
                "tin": "1000000000",
                "email": "info@nasil.com",
                "phone": "+256700000000",
                "website": "https://www.nasil.com",
                "address": "Kampala, Uganda",
            },
        )

        self.stdout.write(self.style.SUCCESS("✓ Company ready"))

        # ------------------------------------------------------------------
        # BRANCH
        # ------------------------------------------------------------------

        branch, _ = Branch.objects.get_or_create(
            code="HQ",
            defaults={
                "company": company,
                "name": "Head Office",
                "city": "Kampala",
                "country": "Uganda",
                "address": "Head Office",
                "phone": "+256700000000",
                "email": "hq@nasil.com",
            },
        )

        self.stdout.write(self.style.SUCCESS("✓ Head Office ready"))

        # ------------------------------------------------------------------
        # DEPARTMENTS
        # ------------------------------------------------------------------

        departments = [
            ("ADMIN", "Administration"),
            ("OPERATIONS", "Operations"),
            ("DISPATCH", "Dispatch"),
            ("WAREHOUSE", "Warehouse"),
            ("FINANCE", "Finance"),
            ("SALES", "Sales"),
            ("HR", "Human Resources"),
            ("IT", "Information Technology"),
        ]

        for code, name in departments:

            Department.objects.get_or_create(
                code=code,
                defaults={
                    "branch": branch,
                    "name": name,
                },
            )

        self.stdout.write(self.style.SUCCESS("✓ Departments ready"))

        # ------------------------------------------------------------------
        # WAREHOUSE
        # ------------------------------------------------------------------

        Warehouse.objects.get_or_create(
            code="MAIN",
            defaults={
                "branch": branch,
                "name": "Main Warehouse",
                "location": "Kampala",
                "capacity": 10000,
            },
        )

        self.stdout.write(self.style.SUCCESS("✓ Warehouse ready"))

        # ------------------------------------------------------------------
        # DJANGO GROUPS
        # ------------------------------------------------------------------

        groups = [
            "Administrator",
            "Operations Manager",
            "Dispatcher",
            "Finance Officer",
            "Warehouse Officer",
            "Sales Officer",
            "HR Officer",
            "IT Support",
        ]

        for group in groups:
            Group.objects.get_or_create(name=group)

        self.stdout.write(self.style.SUCCESS("✓ Security Groups ready"))

        self.stdout.write(
            self.style.SUCCESS("\nSystem successfully seeded.\n")
        )