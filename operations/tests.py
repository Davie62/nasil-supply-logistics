import csv
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from pypdf import PdfReader

from accounts.models import User, EmployeeProfile
from core.business_rules import approval_limit
from core.models import AuditRecord, ContactMessage
from core.test_helpers import booked_shipment
from customers.models import Customer
from organization.models import Company, Branch, Department, Warehouse
from quotations.models import Quote
from quotations.workflows import create_quote, update_quote
from .models import BusinessSettings, DeliveryProof, InventoryItem, OperationsEvent, StockMovement
from .services import deactivate_staff, move_stock, record_delivery_proof, save_inventory, save_settings, save_staff


def image_upload():
    buffer = BytesIO()
    Image.new("RGB", (160, 50), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("signed-note.png", buffer.getvalue(), content_type="image/png")


class OperationsTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="NASIL QA", registration_number="OPS-QA", tin="OPS-QA", email="qa@example.com", phone="0700000000", address="Kampala")
        branch = Branch.objects.create(company=company, name="Kampala", code="OPS-KLA", city="Kampala", country="Uganda", address="Kampala", phone="0700000000", email="branch@example.com")
        self.department = Department.objects.create(branch=branch, name="Operations", code="OPS")
        self.warehouse = Warehouse.objects.create(branch=branch, name="Central warehouse", code="OPS-WH", location="Kampala")
        self.admin = User.objects.create_user(username="ops-admin", email="ops-admin@example.com", is_staff=True, is_superuser=True)
        self.viewer = User.objects.create_user(username="ops-viewer", email="ops-viewer@example.com", is_staff=True)
        self.customer = Customer.objects.create(full_name="Operations Customer", email="ops-customer@example.com", phone="0700000000")
        self.client.force_login(self.admin)

    def grant(self, user, *permissions):
        user.user_permissions.add(*Permission.objects.filter(codename__in=permissions))
        for key in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            user.__dict__.pop(key, None)

    def item(self, **extra):
        return save_inventory(actor=self.admin, data={"sku": "BOX-001", "name": "Shipping boxes", "warehouse": self.warehouse, "unit": "boxes", "reorder_level": 5, "is_active": True, **extra})

    def staff_data(self, **extra):
        return {"username": "new-staff", "email": "new-staff@example.com", "first_name": "Amina", "last_name": "Namusoke", "department": self.department, "position": "Dispatcher", "phone_number": None, "hire_date": timezone.localdate(), "status": "ACTIVE", "password": "A-strong-staff-password-2026!", **extra}

    def settings_data(self, **extra):
        return {"local_currency": "UGX", "international_currency": "USD", "ugx_approval_threshold": 50000000, "usd_approval_threshold": 15000, "notify_quotations": True, "notify_enquiries": True, "notify_overdue": True, **extra}

    def proof(self):
        shipment = booked_shipment(self.customer, status="delivered")
        return record_delivery_proof(actor=self.admin, shipment_id=shipment.pk, recipient_name="Amina", delivered_at=timezone.now(), notes="Received in good condition.", evidence=image_upload())

    def test_detail_screens_include_current_record_and_traceability(self):
        shipment = booked_shipment(self.customer)
        item = self.item()
        for name, pk, text in [("quotation_detail", shipment.quote_id, shipment.quote.quote_number), ("shipment_detail", shipment.pk, shipment.tracking_number), ("inventory_detail", item.pk, item.sku), ("staff_detail", self.admin.profile.pk, self.admin.profile.employee_id)]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=[pk]))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
                self.assertContains(response, "Audit history")
                self.assertContains(response, "EAT")

    def test_new_endpoints_require_staff_permissions(self):
        self.client.force_login(self.viewer)
        for name, args in [("inventory_list", []), ("inventory_create", []), ("inventory_detail", [999]), ("staff_list", []), ("staff_create", []), ("staff_update", [999]), ("operations_reports", []), ("operations_settings", []), ("proof_detail", [999]), ("proof_evidence", [999]), ("proof_export", [999, "pdf"])]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)

    def test_list_search_and_pagination_are_server_side(self):
        for index in range(31):
            Quote.objects.create(customer=self.customer, pickup_location="Kampala", destination=f"Destination {index:02}", cargo_description="Goods", weight=1)
        response = self.client.get(reverse("quotation_list"), {"q": "Destination", "page": 2})
        self.assertEqual(len(response.context["rows"]), 6)
        self.assertEqual(response.context["page_obj"].paginator.count, 31)
        self.assertContains(response, "q=Destination")
        response = self.client.get(reverse("quotation_list"), {"q": "Destination 30"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(len(response.context["rows"]), 1)
        response = self.client.get(reverse("quotation_list"), {"q": "no match"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_inventory_receipts_issues_and_negative_stock_rejection(self):
        item = self.item()
        receipt = move_stock(actor=self.admin, item_id=item.pk, quantity_change="12.500", reason="Supplier receipt", expected_version=item.version)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("12.500"))
        move_stock(actor=self.admin, item_id=item.pk, quantity_change="-2.500", reason="Packing use", expected_version=item.version)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 10)
        with self.assertRaises(ValidationError):
            move_stock(actor=self.admin, item_id=item.pk, quantity_change="-11", reason="Too much", expected_version=item.version)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.movements.count(), 2)
        self.assertEqual(receipt.balance_after, Decimal("12.500"))

    def test_stock_rejects_stale_zero_nonfinite_and_missing_reason(self):
        item = self.item()
        for value, reason, version in [(0, "Zero", item.version), ("NaN", "Invalid", item.version), ("1e100", "Large", item.version), (1, "", item.version), (1, "Stale", item.version - 1)]:
            with self.subTest(value=value, reason=reason), self.assertRaises(ValidationError):
                move_stock(actor=self.admin, item_id=item.pk, quantity_change=value, reason=reason, expected_version=version)
        self.assertFalse(StockMovement.objects.exists())

    def test_inventory_ledger_and_balance_roll_back_if_audit_fails(self):
        item = self.item()
        with patch("operations.services.event", side_effect=RuntimeError("Audit failed")):
            with self.assertRaises(RuntimeError):
                move_stock(actor=self.admin, item_id=item.pk, quantity_change=5, reason="Receipt", expected_version=item.version)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 0)
        self.assertFalse(StockMovement.objects.exists())

    def test_inventory_archive_and_guarded_writes(self):
        item = self.item()
        with self.assertRaises(ValidationError):
            item.save()
        with self.assertRaises(ValidationError):
            InventoryItem.objects.filter(pk=item.pk).update(quantity=999)
        with self.assertRaises(ValidationError):
            item.delete()
        item = save_inventory(actor=self.admin, item_id=item.pk, data={"is_active": False}, expected_version=item.version)
        with self.assertRaises(ValidationError):
            move_stock(actor=self.admin, item_id=item.pk, quantity_change=1, reason="Archived", expected_version=item.version)

    def test_stock_movement_endpoint_is_post_and_csrf_protected(self):
        item = self.item()
        self.assertEqual(self.client.get(reverse("inventory_move", args=[item.pk])).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("inventory_move", args=[item.pk]), {}).status_code, 403)

    def test_staff_create_update_and_deactivate_retain_user_and_profile(self):
        profile = save_staff(actor=self.admin, data=self.staff_data())
        self.assertTrue(profile.user.is_staff)
        self.assertTrue(profile.user.check_password(self.staff_data()["password"]))
        self.assertEqual(profile.branch, self.department.branch)
        self.assertEqual(profile.user.groups.count(), 0)
        data = self.staff_data(position="Senior Dispatcher", password="")
        profile = save_staff(actor=self.admin, profile_id=profile.pk, data=data, expected_version=profile.updated_at.isoformat())
        self.assertEqual(profile.position, "Senior Dispatcher")
        profile = deactivate_staff(actor=self.admin, profile_id=profile.pk, expected_version=profile.updated_at.isoformat(), reason="Contract ended")
        profile.user.refresh_from_db()
        self.assertFalse(profile.user.is_active)
        self.assertEqual(profile.status, "TERMINATED")
        self.assertTrue(User.objects.filter(pk=profile.user_id).exists())
        self.assertEqual(OperationsEvent.objects.filter(entity_type="staff", entity_id=str(profile.pk)).count(), 3)

    def test_staff_rejects_privilege_fields_and_self_deactivation(self):
        with self.assertRaises(ValidationError):
            save_staff(actor=self.admin, data=self.staff_data(is_superuser=True))
        with self.assertRaises(ValidationError):
            deactivate_staff(actor=self.admin, profile_id=self.admin.profile.pk, expected_version=self.admin.profile.updated_at.isoformat(), reason="Self")

    def test_hr_cannot_edit_privileged_account(self):
        self.grant(self.viewer, "change_employeeprofile", "view_employeeprofile")
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("staff_update", args=[self.admin.profile.pk])).status_code, 403)

    def test_staff_form_rejects_duplicate_contacts_and_weak_password(self):
        data = self.staff_data(email=self.admin.email, password="123")
        data["phone_number"] = ""
        data["department"] = self.department.pk
        response = self.client.post(reverse("staff_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertIn("password", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="new-staff").exists())

    def test_settings_change_thresholds_and_notification_preferences_immediately(self):
        ContactMessage.objects.create(name="Amina", email="message@example.com", subject="Question", message="Please call.")
        self.assertGreater(self.client.get(reverse("dashboard")).context["notification_count"], 0)
        policy = save_settings(actor=self.admin, data=self.settings_data(ugx_approval_threshold=90000000, notify_enquiries=False), expected_version=0)
        self.assertEqual(approval_limit("UGX"), Decimal("90000000"))
        self.assertEqual(self.client.get(reverse("dashboard")).context["notification_count"], 0)
        with self.assertRaises(ValidationError):
            save_settings(actor=self.admin, data=self.settings_data(), expected_version=0)
        self.assertEqual(policy.version, 1)

    def test_currency_settings_affect_new_quotes_and_preserve_existing_currency(self):
        data = {"customer": self.customer, "pickup_location": "A", "destination": "B", "cargo_description": "Goods", "weight": 1}
        quote = create_quote(actor=self.admin, data=data)
        save_settings(actor=self.admin, data=self.settings_data(local_currency="USD", international_currency="UGX"), expected_version=0)
        new_quote = create_quote(actor=self.admin, data=data)
        self.assertEqual(new_quote.currency, "USD")
        quote = update_quote(actor=self.admin, quote_id=quote.pk, data={"base_amount": 100})
        self.assertEqual(quote.currency, "UGX")

    def test_non_admin_cannot_change_policy_even_with_permission(self):
        self.grant(self.viewer, "view_businesssettings", "change_businesssettings")
        with self.assertRaises(PermissionDenied):
            save_settings(actor=self.viewer, data=self.settings_data(), expected_version=0)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("operations_settings")).status_code, 403)

    def test_settings_reject_negative_thresholds_without_partial_save(self):
        with self.assertRaises(ValidationError):
            save_settings(actor=self.admin, data=self.settings_data(ugx_approval_threshold=-1), expected_version=0)
        self.assertFalse(BusinessSettings.objects.exists())
        self.assertFalse(OperationsEvent.objects.exists())

    def test_proof_private_storage_hash_and_immutable_history(self):
        proof = self.proof()
        self.assertEqual(len(proof.evidence_sha256), 64)
        self.assertTrue(proof.shipment.history.filter(action="delivery_proof_recorded").exists())
        self.assertNotIn("/media/", self.client.get(reverse("proof_detail", args=[proof.pk])).content.decode())
        response = self.client.get(reverse("proof_evidence", args=[proof.pk]))
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertEqual(b"".join(response.streaming_content), bytes(proof.evidence))
        with self.assertRaises(ValidationError):
            proof.save()

    def test_proof_requires_delivered_shipment_and_valid_evidence(self):
        shipment = booked_shipment(self.customer)
        values = dict(actor=self.admin, shipment_id=shipment.pk, recipient_name="Amina", delivered_at=timezone.now(), notes="", evidence=image_upload())
        with self.assertRaises(ValidationError):
            record_delivery_proof(**values)
        shipment = booked_shipment(self.customer, status="delivered")
        for file in [SimpleUploadedFile("payload.html", b"<script>alert(1)</script>", content_type="image/png"), SimpleUploadedFile("bad.pdf", b"%PDF-broken"), SimpleUploadedFile("huge.png", b"x" * (5 * 1024 * 1024 + 1))]:
            with self.subTest(file=file.name), self.assertRaises(ValidationError):
                record_delivery_proof(**{**values, "shipment_id": shipment.pk, "evidence": file})
        self.assertFalse(DeliveryProof.objects.exists())

    def test_proof_rejects_future_time_and_overwrite(self):
        proof = self.proof()
        for when in (timezone.now() + timedelta(days=1), timezone.now()):
            with self.assertRaises(ValidationError):
                record_delivery_proof(actor=self.admin, shipment_id=proof.shipment_id, recipient_name="Replacement", delivered_at=when, notes="", evidence=image_upload())
        self.assertEqual(DeliveryProof.objects.get().recipient_name, "Amina")

    def test_proof_download_requires_both_evidence_and_shipment_permission(self):
        proof = self.proof()
        self.grant(self.viewer, "view_deliveryproof")
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("proof_evidence", args=[proof.pk])).status_code, 403)

    def test_proof_csv_pdf_headers_and_audit_references(self):
        proof = self.proof()
        for format in ("csv", "pdf"):
            response = self.client.get(reverse("proof_export", args=[proof.pk, format]))
            self.assertEqual(response.status_code, 200)
            self.assertIn("X-Audit-Reference", response)
            if format == "pdf":
                text = "".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
            else:
                text = response.content.decode("utf-8-sig")
            self.assertIn(str(proof.reference), text)
            self.assertIn(proof.evidence_sha256, text.replace("\n", ""))
            self.assertIn("Generated", text)

    def test_reports_filter_status_staff_dates_and_export_same_records(self):
        shipment = booked_shipment(self.customer)
        booked_shipment(self.customer, status="delivered")
        today = timezone.localdate().isoformat()
        filters = {"report": "shipments", "status": "pending", "date_from": today, "date_to": today, "staff": shipment.created_by_id}
        response = self.client.get(reverse("operations_reports"), filters)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["rows"][0]["values"][0], shipment.tracking_number)
        response = self.client.get(reverse("operations_reports"), {**filters, "format": "csv"})
        rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[-1][0], shipment.tracking_number)
        self.assertIn("AUD-", rows[-1][-1])

    def test_report_type_is_permission_checked_and_export_is_separate(self):
        self.grant(self.viewer, "view_reports", "view_inventoryitem")
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("operations_reports"), {"report": "staff"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("operations_reports"), {"report": "inventory", "format": "csv"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("operations_reports"), {"report": "inventory"}).status_code, 200)

    def test_invalid_report_filters_return_no_data_and_cannot_export(self):
        booked_shipment(self.customer)
        for filters in ({"date_from": "bad"}, {"date_from": "2026-10-28", "date_to": "2026-10-27"}, {"status": "invalid"}, {"date_to": "9999-12-31"}):
            with self.subTest(filters=filters):
                response = self.client.get(reverse("operations_reports"), {"report": "shipments", **filters})
                self.assertEqual(response.context["page_obj"].paginator.count, 0)
                self.assertEqual(self.client.get(reverse("operations_reports"), {"report": "shipments", "format": "csv", **filters}).status_code, 400)

    def test_all_report_types_render_and_pdf_is_valid(self):
        self.item()
        self.proof()
        for kind in ("quotations", "shipments", "inventory", "staff", "proofs"):
            with self.subTest(kind=kind):
                self.assertEqual(self.client.get(reverse("operations_reports"), {"report": kind}).status_code, 200)
                response = self.client.get(reverse("operations_reports"), {"report": kind, "format": "pdf"})
                self.assertGreaterEqual(len(PdfReader(BytesIO(response.content)).pages), 1)

    def test_csv_neutralizes_formula_injection(self):
        self.customer.full_name = "=HYPERLINK(\"https://example.com\")"
        self.customer.save()
        booked_shipment(self.customer)
        response = self.client.get(reverse("operations_reports"), {"report": "shipments", "format": "csv"})
        rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertTrue(rows[-1][1].startswith("'="))

    def test_report_queries_do_not_grow_with_page_rows(self):
        self.item()
        with CaptureQueriesContext(connection) as small:
            self.client.get(reverse("operations_reports"), {"report": "inventory"})
        for index in range(12):
            self.item(sku=f"BOX-{index + 100}")
        with CaptureQueriesContext(connection) as large:
            self.client.get(reverse("operations_reports"), {"report": "inventory"})
        self.assertLessEqual(len(large), len(small) + 1)

    def test_operations_audit_is_append_only(self):
        item = self.item()
        audit = OperationsEvent.objects.get(entity_type="inventory", entity_id=str(item.pk))
        with self.assertRaises(ValidationError):
            audit.save()
        with self.assertRaises(ValueError):
            OperationsEvent.objects.filter(pk=audit.pk).update(action="modified")

    def test_inventory_form_create_and_adjustment_post(self):
        response = self.client.post(reverse("inventory_create"), {"sku": "NEW-001", "name": "Crates", "warehouse": self.warehouse.pk, "unit": "crates", "reorder_level": "2", "is_active": "on"})
        item = InventoryItem.objects.get(sku="NEW-001")
        self.assertRedirects(response, reverse("inventory_detail", args=[item.pk]))
        response = self.client.post(reverse("inventory_move", args=[item.pk]), {"quantity_change": "3", "reason": "Receipt", "record_version": item.version})
        self.assertRedirects(response, reverse("inventory_detail", args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_staff_form_successful_submission(self):
        data = self.staff_data()
        data.update(phone_number="", department=self.department.pk)
        response = self.client.post(reverse("staff_create"), data)
        profile = EmployeeProfile.objects.get(user__username="new-staff")
        self.assertRedirects(response, reverse("staff_detail", args=[profile.pk]))

    def test_settings_form_successful_submission(self):
        response = self.client.post(reverse("operations_settings"), {**self.settings_data(), "record_version": 0})
        self.assertRedirects(response, reverse("operations_settings"))
        self.assertEqual(BusinessSettings.objects.get().version, 1)

    def test_delivery_proof_form_accepts_private_multipart_upload(self):
        shipment = booked_shipment(self.customer, status="delivered")
        response = self.client.post(reverse("proof_create", args=[shipment.pk]), {"recipient_name": "Amina", "delivered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S"), "notes": "Signed", "evidence": image_upload()})
        proof = DeliveryProof.objects.get()
        self.assertRedirects(response, reverse("proof_detail", args=[proof.pk]))

    def test_existing_staff_credentials_require_superuser(self):
        self.grant(self.viewer, "change_employeeprofile")
        profile = save_staff(actor=self.admin, data=self.staff_data())
        with self.assertRaises(PermissionDenied):
            save_staff(actor=self.viewer, profile_id=profile.pk, expected_version=profile.updated_at.isoformat(), data=self.staff_data(password="A-new-strong-password-2026!"))
