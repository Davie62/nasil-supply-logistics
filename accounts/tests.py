from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


@override_settings(SECURE_SSL_REDIRECT=False)
class AuthenticationSecurityTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="security-user",
			email="security@example.com",
			password="Strong-password-123",
		)

	def test_logout_requires_post(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("logout"))
		self.assertEqual(response.status_code, 405)
		self.assertTrue(response.wsgi_request.user.is_authenticated)

	def test_repeated_failed_logins_lock_account(self):
		for _ in range(5):
			response = self.client.post(reverse("login"), {
				"username": self.user.username,
				"password": "incorrect-password",
			})
			self.assertEqual(response.status_code, 200)

		self.user.refresh_from_db()
		self.assertEqual(self.user.failed_login_attempts, 5)
		self.assertIsNotNone(self.user.locked_until)

		response = self.client.post(reverse("login"), {
			"username": self.user.username,
			"password": "Strong-password-123",
		})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.wsgi_request.user.is_authenticated)


class EmployeeProvisioningTests(TestCase):
    def setUp(self):
        from organization.models import Company, Branch, Department
        company = Company.objects.create(name="NASIL", registration_number="REG1", tin="TIN1", email="info@example.com", phone="0700000000", address="Kampala")
        self.branch = Branch.objects.create(company=company, name="HQ", code="HQ", city="Kampala", country="Uganda", address="Kampala", phone="0700000000", email="hq@example.com")
        self.department = Department.objects.create(branch=self.branch, name="Operations", code="OPS")

    def test_multiple_staff_receive_unique_ids_and_can_omit_phone(self):
        from .models import EmployeeProfile
        from django.utils import timezone
        first = User.objects.create_user(username="first", email="first@example.com", is_staff=True)
        second = User.objects.create_user(username="second", email="second@example.com", is_staff=True)
        self.assertEqual(first.profile.employee_id, f"NSL-{timezone.localdate().year}-00001")
        self.assertEqual(second.profile.employee_id, f"NSL-{timezone.localdate().year}-00002")
        self.assertIsNone(first.profile.phone_number)
        self.assertIsNone(second.profile.phone_number)
        self.assertEqual(EmployeeProfile.objects.count(), 2)

    def test_nonstaff_not_provisioned_and_promotion_provisions_once(self):
        from .models import EmployeeProfile
        user = User.objects.create_user(username="customer", email="customer@example.com")
        self.assertFalse(EmployeeProfile.objects.filter(user=user).exists())
        user.is_staff = True
        user.save()
        user.save()
        self.assertEqual(EmployeeProfile.objects.filter(user=user).count(), 1)

    def test_profile_uses_department_branch_and_service_is_idempotent(self):
        from .services import EmployeeService
        user = User.objects.create_user(username="employee", email="employee@example.com", is_staff=True)
        profile = EmployeeService.create_employee_profile(user)
        self.assertEqual(profile.pk, user.profile.pk)
        self.assertEqual(profile.branch_id, profile.department.branch_id)

    def test_sequence_does_not_reuse_deleted_employee_id(self):
        from .services import EmployeeService
        user = User.objects.create_user(username="employee", email="employee@example.com", is_staff=True)
        identifier = user.profile.employee_id
        user.profile.delete()
        self.assertNotEqual(EmployeeService.generate_employee_id(), identifier)

    def test_blank_phone_is_normalized_on_update(self):
        user = User.objects.create_user(username="employee", email="employee@example.com", is_staff=True)
        profile = user.profile
        profile.phone_number = ""
        profile.save()
        profile.refresh_from_db()
        self.assertIsNone(profile.phone_number)


class RoleDefaultsTests(TestCase):
    def test_seed_assigns_business_permissions_without_user_administration(self):
        from django.core.management import call_command
        from django.contrib.auth.models import Group
        from io import StringIO
        call_command("seed_system", stdout=StringIO())
        dispatcher = Group.objects.get(name="Dispatcher")
        self.assertTrue(dispatcher.permissions.filter(codename="change_shipment").exists())
        self.assertFalse(dispatcher.permissions.filter(codename="change_quote").exists())
        for group in Group.objects.all():
            self.assertFalse(group.permissions.filter(content_type__app_label="auth").exists())
            self.assertFalse(group.permissions.filter(content_type__app_label="accounts", content_type__model="user").exists())
        # Rerunning seeding must preserve explicit administrator additions.
        from django.contrib.auth.models import Permission
        custom = Permission.objects.get(codename="change_quote")
        dispatcher.permissions.add(custom)
        call_command("seed_system", stdout=StringIO())
        self.assertTrue(dispatcher.permissions.filter(pk=custom.pk).exists())


class EmployeeMigrationBackfillTests(TestCase):
    def test_backfill_uses_highest_legacy_number_and_normalizes_blank_phone(self):
        import importlib
        from types import SimpleNamespace
        from django.apps import apps
        from django.db import connection
        from django.utils import timezone
        from organization.models import Company, Branch, Department
        from .models import EmployeeIDSequence, EmployeeProfile
        from .services import EmployeeService
        company = Company.objects.create(name="NASIL", registration_number="LEGACY", tin="LEGACY", email="legacy@example.com", phone="0700000000", address="Kampala")
        branch = Branch.objects.create(company=company, name="HQ", code="LEGACY", city="Kampala", country="Uganda", address="Kampala", phone="0700000000", email="hq@example.com")
        department = Department.objects.create(branch=branch, name="Operations", code="LEGACY")
        user = User.objects.create_user(username="legacy", email="legacy@example.com")
        year = timezone.localdate().year
        profile = EmployeeProfile.objects.create(user=user, employee_id=f"NSL-{year}-00125", branch=branch, department=department, position="Officer")
        EmployeeProfile.objects.filter(pk=profile.pk).update(phone_number="")
        migration = importlib.import_module("accounts.migrations.0003_employee_identifiers")
        migration.initialize_sequences(apps, SimpleNamespace(connection=connection))
        profile.refresh_from_db()
        self.assertIsNone(profile.phone_number)
        self.assertEqual(EmployeeIDSequence.objects.get(year=year).last_number, 125)
        self.assertEqual(EmployeeService.generate_employee_id(), f"NSL-{year}-00126")


class AdminUserCreationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="root", email="root@example.com", password="Strong-password-123")
        self.client.force_login(self.admin)

    def test_admin_can_create_multiple_staff_with_required_unique_email(self):
        for index in (1, 2):
            response = self.client.post(reverse("admin:accounts_user_add"), {
                "username": f"staff{index}", "email": f"staff{index}@example.com",
                "is_staff": "on", "usable_password": "true",
                "password1": "Strong-staff-password-123", "password2": "Strong-staff-password-123",
            })
            self.assertEqual(response.status_code, 302)
            self.assertTrue(User.objects.get(username=f"staff{index}").is_staff)

    def test_admin_rejects_missing_email_before_saving(self):
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "username": "missing-email", "usable_password": "true",
            "password1": "Strong-staff-password-123", "password2": "Strong-staff-password-123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["adminform"].form.errors)
        self.assertFalse(User.objects.filter(username="missing-email").exists())
