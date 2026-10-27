from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import User
from customers.models import Customer
from quotations.models import Quote
from shipments.models import Shipment
from core.test_helpers import booked_shipment


class DashboardModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dashboard-user", email="dashboard@example.com", is_staff=True)

    def test_modules_require_authentication(self):
        for module in ("shipments", "quotations", "employees", "reports", "settings"):
            response = self.client.get(reverse(f"dashboard_{module}"))
            self.assertRedirects(response, f"/accounts/login/?next=/dashboard/{module}/")

    def test_existing_modules_redirect_to_correct_destination(self):
        self.user.user_permissions.add(*Permission.objects.filter(codename__startswith="view_"))
        self.client.force_login(self.user)
        for module, target in (("shipments", "shipment_list"), ("quotations", "quotation_list"), ("employees", "staff_list")):
            self.assertRedirects(self.client.get(reverse(f"dashboard_{module}")), reverse(target))

    def test_completed_modules_route_to_permission_checked_screens(self):
        self.client.force_login(self.user)
        for module, target in (("reports", "operations_reports"), ("settings", "operations_settings")):
            response = self.client.get(reverse(f"dashboard_{module}"))
            self.assertRedirects(response, reverse(target), fetch_redirect_response=False)
            self.assertEqual(self.client.get(reverse(target)).status_code, 403)

    def test_payments_is_not_enabled(self):
        with self.assertRaises(NoReverseMatch):
            reverse("payments")

    def test_dashboard_has_no_unauthorized_metrics_or_misleading_actions(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertNotIn("shipment_count", response.context)
        self.assertNotIn("employee_count", response.context)
        self.assertNotContains(response, "Record Payment")
        self.assertNotContains(response, "Add Employee")
        self.assertNotContains(response, "Shipment status distribution")
        self.assertNotContains(response, "<span>Administrator</span>", html=True)

    def test_chart_uses_actual_status_counts_including_cancelled(self):
        self.user.user_permissions.add(Permission.objects.get(codename="view_shipment"))
        customer = Customer.objects.create(full_name="Amina", email="amina@example.com", phone="0700000000")
        for status in ("pending", "delivered", "delivered", "cancelled"):
            booked_shipment(customer, status=status)
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["shipment_count"], 4)
        self.assertEqual(response.context["active_shipments"], 1)
        self.assertEqual(response.context["status_counts"]["cancelled"], 1)
        self.assertIn("var(--warning) 0.00% 25.00%", response.context["shipment_gradient"])
        self.assertIn("var(--success) 25.00% 75.00%", response.context["shipment_gradient"])

    def test_empty_chart_is_neutral(self):
        self.user.user_permissions.add(Permission.objects.get(codename="view_shipment"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["shipment_count"], 0)
        self.assertEqual(response.context["shipment_gradient"], "var(--border-color, #e5e7eb)")


class DashboardOperationalDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operations", email="operations@example.com", is_staff=True)
        self.customer = Customer.objects.create(full_name="Private Customer", email="private@example.com", phone="0700000000")
        self.client.force_login(self.user)

    def grant(self, *codenames):
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))

    def shipment(self, days_ago=0, status="pending", overdue=False):
        from datetime import timedelta
        from django.utils import timezone
        from unittest.mock import patch
        from shipments.workflows import update_shipment
        # Book an ETA while it is still in the future, then observe it today.
        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now - timedelta(days=days_ago)), patch('shipments.workflows.timezone.localdate', return_value=timezone.localdate() - timedelta(days=10)):
            shipment = booked_shipment(self.customer)
            if overdue:
                shipment = update_shipment(shipment_id=shipment.pk, actor=shipment.created_by, estimated_delivery=timezone.localdate() + timedelta(days=9))
            if status != 'pending':
                from shipments.workflows import transition_shipment
                if status in {'in_transit', 'delivered'}:
                    shipment = transition_shipment(shipment_id=shipment.pk, actor=shipment.created_by, target='in_transit')
                if status in {'delivered', 'cancelled'}:
                    shipment = transition_shipment(shipment_id=shipment.pk, actor=shipment.created_by, target=status, reason='Fixture closure')
        return shipment

    def test_booking_chart_respects_range_and_excludes_older_records(self):
        self.grant("view_shipment")
        self.shipment()
        self.shipment(days_ago=8)
        self.shipment(days_ago=8)
        self.shipment(days_ago=40)
        for period, total in (("7", 1), ("30", 3), ("90", 4)):
            with self.subTest(period=period):
                response = self.client.get(reverse("dashboard"), {"range": period})
                self.assertEqual(response.context["shipment_trend"]["total"], total)
                self.assertEqual(response.context["range_days"], int(period))
                self.assertEqual(len(response.context["shipment_trend"]["points"].split()), int(period))
        self.assertEqual(response.context["shipment_trend"]["peak"], 2)

    def test_invalid_date_ranges_fall_back_to_thirty_days(self):
        self.grant("view_shipment")
        for period in ("0", "-1", "999999999", "invalid"):
            with self.subTest(period=period):
                response = self.client.get(reverse("dashboard"), {"range": period})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["range_days"], 30)
                self.assertEqual(response.context["shipment_trend"]["total"], 0)

    def test_recent_shipments_and_chart_are_absent_without_permission(self):
        shipment = self.shipment()
        response = self.client.get(reverse("dashboard"))
        self.assertNotIn("recent_shipments", response.context)
        self.assertNotIn("shipment_trend", response.context)
        self.assertNotContains(response, shipment.tracking_number)
        self.assertNotContains(response, "Private Customer")

    def test_read_only_shipments_show_records_without_edit_links(self):
        self.grant("view_shipment")
        shipment = self.shipment()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, shipment.tracking_number)
        self.assertNotContains(response, reverse("shipment_update", args=[shipment.pk]))
        self.assertNotContains(response, reverse("shipment_create"))

    def test_notifications_are_permission_filtered_and_exclude_completed_shipments(self):
        from core.models import ContactMessage
        ContactMessage.objects.create(name="Private Enquiry", email="private@example.com", subject="Private Subject", message="Please call.")
        Quote.objects.create(customer=self.customer, pickup_location="Kampala", destination="Jinja", cargo_description="Goods", weight=10, status="pending")
        self.shipment(overdue=True)
        self.shipment(status="delivered", overdue=True)
        self.grant("view_contactmessage")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["notification_count"], 1)
        self.assertEqual([item["label"] for item in response.context["operational_notifications"]], ["Unread enquiries"])
        self.assertNotContains(response, "Private Subject")
        self.grant("view_quote", "view_shipment")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["notification_count"], 3)
        self.assertEqual(len(response.context["operational_notifications"]), 3)

    def test_notification_count_updates_after_enquiry_is_marked_read(self):
        from core.models import ContactMessage
        self.grant("view_contactmessage", "change_contactmessage")
        message = ContactMessage.objects.create(name="Amina", email="amina@example.com", subject="Delivery", message="Please call.")
        self.assertEqual(self.client.get(reverse("dashboard")).context["notification_count"], 1)
        self.client.post(reverse("contact_message_read", args=[message.pk]))
        self.assertEqual(self.client.get(reverse("dashboard")).context["notification_count"], 0)

    def test_operational_drilldowns_filter_the_actual_records(self):
        from core.models import ContactMessage
        self.grant("view_shipment", "view_quote", "view_contactmessage")
        overdue = self.shipment(overdue=True)
        self.shipment(overdue=True, status="delivered")
        self.shipment()
        response = self.client.get(reverse("shipment_list"), {"overdue": "1"})
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertEqual(response.context["rows"][0]["values"][0], overdue.tracking_number)
        self.assertEqual(response.context["active_filter"], "Overdue shipments")
        self.assertEqual(len(self.client.get(reverse("shipment_list"), {"status": "pending"}).context["rows"]), 2)
        self.assertEqual(len(self.client.get(reverse("shipment_list"), {"status": "invalid"}).context["rows"]), 3)
        Quote.objects.create(customer=self.customer, pickup_location="Kampala", destination="Jinja", cargo_description="Goods", weight=10, status="pending")
        self.assertEqual(len(self.client.get(reverse("quotation_list"), {"status": "pending"}).context["rows"]), 1)
        ContactMessage.objects.create(name="Unread", email="unread@example.com", subject="Enquiry", message="Hello")
        ContactMessage.objects.create(name="Read", email="read@example.com", subject="Enquiry", message="Hello", is_read=True)
        self.assertEqual(len(self.client.get(reverse("contact_message_list"), {"unread": "1"}).context["rows"]), 1)
