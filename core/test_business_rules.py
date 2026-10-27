from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from customers.models import Customer
from quotations.models import Quote
from quotations.workflows import create_quote, transition_quote, update_quote
from shipments.models import Shipment
from shipments.workflows import convert_quote_to_shipment, transition_shipment, update_shipment
from .business_rules import calculate_price
from .models import AuditRecord


@override_settings(QUOTATION_APPROVAL_THRESHOLDS={"UGX": "1000000", "USD": "1000"})
class CoreBusinessRulesTests(TestCase):
    def setUp(self):
        self.preparer = User.objects.create_user(username="preparer", email="prepare@example.com", is_staff=True)
        self.approver = User.objects.create_user(username="approver", email="approve@example.com", is_staff=True)
        self.admin = User.objects.create_user(username="business-admin", email="admin@example.com", is_staff=True, is_superuser=True)
        self.customer = Customer.objects.create(full_name="Customer", email="customer@example.com", phone="0700000000")
        self.preparer.user_permissions.add(*Permission.objects.filter(codename__in=["add_quote", "change_quote", "view_quote", "add_shipment", "view_shipment", "change_shipment"]))
        self.approver.user_permissions.add(*Permission.objects.filter(codename__in=["view_quote", "approve_quote"]))

    def quote(self, **extra):
        return create_quote(actor=self.preparer, data={"customer": self.customer, "pickup_location": "Kampala", "destination": "Jinja", "cargo_description": "Goods", "weight": Decimal("10"), "base_amount": Decimal("100"), "valid_until": timezone.localdate() + timedelta(days=7), **extra})

    def approved(self, **extra):
        quote = self.quote(**extra)
        transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        return transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")

    def test_price_formula_rounding_and_currency(self):
        quote = self.quote(weight=Decimal("1.25"), base_amount=Decimal("10.01"), rate_per_kg=Decimal("2.25"), surcharge=Decimal("3.33"), discount=Decimal("1.01"), tax_rate=Decimal("18"))
        self.assertEqual((quote.subtotal, quote.tax_amount, quote.total_amount), (Decimal("15.14"), Decimal("2.73"), Decimal("17.87")))
        self.assertEqual(quote.currency, "UGX")
        self.assertEqual(self.quote(trade_type="international").currency, "USD")

    def test_invalid_prices_are_rejected_without_records(self):
        for extra in ({"weight": 0}, {"weight": -1}, {"base_amount": -1}, {"discount": 101}, {"tax_rate": 101}, {"cargo_value": -1}, {"trade_type": "other"}, {"base_amount": Decimal("NaN")}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.quote(**extra)
        self.assertFalse(Quote.objects.exists())
        self.assertFalse(AuditRecord.objects.exists())

    def test_negative_nonfinite_and_excessive_numbers(self):
        values = dict(weight=1, base_amount=1, rate_per_kg=0, surcharge=0, discount=0, tax_rate=0)
        for invalid in ("NaN", "Infinity", "abc", "-1", "999999999999999"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                calculate_price(**{**values, "base_amount": invalid})

    def test_reviewer_cannot_skip_review(self):
        quote = self.quote()
        with self.assertRaises(ValidationError):
            transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")

    def test_own_quotation_cannot_be_approved_even_by_admin(self):
        quote = create_quote(actor=self.admin, data={"customer": self.customer, "pickup_location": "A", "destination": "B", "cargo_description": "Goods", "weight": 1, "base_amount": 1, "valid_until": timezone.localdate()})
        transition_quote(quote_id=quote.pk, actor=self.admin, target="reviewed")
        with self.assertRaises(ValidationError):
            transition_quote(quote_id=quote.pk, actor=self.admin, target="approved")

    def test_public_request_preparer_is_recorded_and_cannot_self_approve(self):
        quote = Quote.objects.create(customer=self.customer, pickup_location="A", destination="B", cargo_description="Goods", weight=1)
        quote = update_quote(quote_id=quote.pk, actor=self.admin, data={"base_amount": 10, "valid_until": timezone.localdate()})
        self.assertEqual(quote.prepared_by, self.admin)
        transition_quote(quote_id=quote.pk, actor=self.admin, target="reviewed")
        with self.assertRaises(ValidationError):
            transition_quote(quote_id=quote.pk, actor=self.admin, target="approved")

    def test_threshold_boundary_and_admin_above_limit(self):
        self.approved(base_amount=Decimal("1000000"))
        quote = self.quote(base_amount=Decimal("1000000.01"))
        transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        with self.assertRaises(PermissionDenied):
            transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")
        self.assertEqual(transition_quote(quote_id=quote.pk, actor=self.admin, target="approved").approved_by, self.admin)

    def test_high_value_permission_without_admin_role_does_not_suffice(self):
        self.approver.user_permissions.add(Permission.objects.get(codename="approve_high_value_quote"))
        quote = self.quote(base_amount=1000001)
        transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        with self.assertRaises(PermissionDenied):
            transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")
        self.approver.groups.add(Group.objects.create(name="Administrator"))
        self.assertEqual(transition_quote(quote_id=quote.pk, actor=self.approver, target="approved").status, "approved")

    def test_usd_uses_separate_threshold(self):
        quote = self.quote(trade_type="international", base_amount=1001)
        transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        with self.assertRaises(PermissionDenied):
            transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")

    @override_settings(QUOTATION_APPROVAL_THRESHOLDS={})
    def test_unconfigured_policy_blocks_approval(self):
        quote = self.quote()
        transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        with self.assertRaisesMessage(ValidationError, "not configured"):
            transition_quote(quote_id=quote.pk, actor=self.admin, target="approved")

    def test_zero_price_and_expired_quote_cannot_be_approved(self):
        for details in ({"base_amount": 0}, {"valid_until": None}, {"valid_until": timezone.localdate() - timedelta(days=1)}):
            quote = self.quote(**details)
            transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
            with self.assertRaises(ValidationError):
                transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")

    def test_approval_edit_lock_and_reopen_clear_approval(self):
        quote = self.approved()
        with self.assertRaises(ValidationError):
            update_quote(quote_id=quote.pk, actor=self.preparer, data={"base_amount": 500})
        with self.assertRaises(ValidationError):
            transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        quote = transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed", reason="Reprice route")
        self.assertIsNone(quote.approved_at)
        self.assertIsNone(quote.approved_by)

    def test_rejection_requires_reason_and_can_resubmit(self):
        quote = self.quote()
        with self.assertRaises(ValidationError):
            transition_quote(quote_id=quote.pk, actor=self.preparer, target="rejected")
        quote = transition_quote(quote_id=quote.pk, actor=self.preparer, target="rejected", reason="Route unavailable")
        self.assertEqual(transition_quote(quote_id=quote.pk, actor=self.preparer, target="pending").status, "pending")

    def test_conversion_requires_approval_is_idempotent_and_records_history(self):
        pending = self.quote()
        with self.assertRaises(ValidationError):
            convert_quote_to_shipment(quote_id=pending.pk, actor=self.preparer)
        quote = self.approved()
        shipment = convert_quote_to_shipment(quote_id=quote.pk, actor=self.preparer)
        repeated = convert_quote_to_shipment(quote_id=quote.pk, actor=self.preparer)
        self.assertEqual(shipment.pk, repeated.pk)
        self.assertEqual(shipment.status, "pending")
        self.assertEqual(shipment.history.count(), 1)
        self.assertEqual(shipment.history.get().action, "converted_from_quote")
        with self.assertRaises(ValidationError):
            transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed", reason="Reprice")

    def test_expired_approved_quote_cannot_be_converted(self):
        quote = self.approved()
        with patch("core.business_rules.timezone.localdate", return_value=timezone.localdate() + timedelta(days=8)):
            with self.assertRaises(ValidationError):
                convert_quote_to_shipment(quote_id=quote.pk, actor=self.preparer)

    def test_valid_delivery_workflow_and_terminal_lock(self):
        shipment = convert_quote_to_shipment(quote_id=self.approved().pk, actor=self.preparer)
        with self.assertRaises(ValidationError):
            transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="delivered")
        shipment = transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="in_transit")
        self.assertIsNotNone(shipment.dispatched_at)
        shipment = transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="delivered")
        self.assertIsNotNone(shipment.delivered_at)
        self.assertEqual(shipment.history.count(), 3)
        self.assertEqual(shipment.history.first().from_status, "in_transit")
        with self.assertRaises(ValidationError):
            update_shipment(shipment_id=shipment.pk, actor=self.preparer, current_location="Elsewhere")

    def test_cancellation_requires_reason(self):
        shipment = convert_quote_to_shipment(quote_id=self.approved().pk, actor=self.preparer)
        with self.assertRaises(ValidationError):
            transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="cancelled")
        shipment = transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="cancelled", reason="Customer request")
        self.assertIsNotNone(shipment.cancelled_at)
        self.assertEqual(shipment.history.first().reason, "Customer request")

    def test_source_quote_and_stale_forms_are_protected(self):
        quote = self.quote()
        update_quote(quote_id=quote.pk, actor=self.preparer, data={"base_amount": 200}, expected_version=quote.version)
        with self.assertRaises(ValidationError):
            update_quote(quote_id=quote.pk, actor=self.preparer, data={"base_amount": 300}, expected_version=quote.version)
        shipment = convert_quote_to_shipment(quote_id=self.approved().pk, actor=self.preparer)
        with self.assertRaises(ValidationError):
            update_shipment(shipment_id=shipment.pk, actor=self.preparer, quote=self.quote())
        transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="in_transit", expected_version=shipment.version)
        with self.assertRaises(ValidationError):
            transition_shipment(shipment_id=shipment.pk, actor=self.preparer, target="cancelled", reason="Stale request", expected_version=shipment.version)

    def test_audit_actor_diffs_and_append_only_behavior(self):
        quote = self.quote()
        update_quote(quote_id=quote.pk, actor=self.preparer, data={"base_amount": Decimal("150")})
        event = quote.audit_records.first()
        self.assertEqual(event.actor, self.preparer)
        self.assertEqual(event.changes["base_amount"]["before"], "100.00")
        self.assertEqual(event.changes["base_amount"]["after"], "150")
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()
        with self.assertRaises(ValueError):
            AuditRecord.objects.filter(pk=event.pk).update(reason="Tampered")
        with self.assertRaises(ValueError):
            AuditRecord.objects.all().delete()
        with self.assertRaises(ProtectedError):
            quote.delete()

    def test_audit_failure_rolls_back_status_and_approval(self):
        quote = self.quote()
        transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        count = quote.audit_records.count()
        with patch("core.signals.AuditRecord.objects.using", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                transition_quote(quote_id=quote.pk, actor=self.approver, target="approved")
        quote.refresh_from_db()
        self.assertEqual(quote.status, "reviewed")
        self.assertIsNone(quote.approved_by)
        self.assertEqual(quote.audit_records.count(), count)

    def test_direct_and_bulk_writes_cannot_bypass_workflow(self):
        quote = self.quote()
        quote.status = "approved"
        with self.assertRaises(ValidationError):
            quote.save()
        with self.assertRaises(ValidationError):
            Quote.objects.filter(pk=quote.pk).update(status="approved")
        with self.assertRaises(ValidationError):
            Quote.objects.bulk_update([quote], ["status"])
        with self.assertRaises(ValidationError):
            Shipment.objects.create(quote=quote)
        with self.assertRaises(ValidationError):
            Shipment.objects.bulk_create([Shipment(quote=quote)])

    def test_services_enforce_permissions_for_nonstaff_and_missing_grants(self):
        quote = self.quote()
        with self.assertRaises(PermissionDenied):
            update_quote(quote_id=quote.pk, actor=self.approver, data={"base_amount": 1})
        self.admin.is_staff = False
        with self.assertRaises(PermissionDenied):
            transition_quote(quote_id=quote.pk, actor=self.admin, target="reviewed")

    def test_approval_only_user_can_use_view_but_cannot_edit_terms(self):
        quote = self.quote()
        quote = transition_quote(quote_id=quote.pk, actor=self.preparer, target="reviewed")
        self.client.force_login(self.approver)
        url = reverse("quotation_update", args=[quote.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(self.client.post(url, {"workflow_action": "approved", "record_version": quote.version}), url)
        self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_view_rejects_forged_approval_and_shipment_transitions(self):
        quote = self.quote()
        self.client.force_login(self.preparer)
        url = reverse("quotation_update", args=[quote.pk])
        self.assertEqual(self.client.post(url, {"workflow_action": "approved", "record_version": quote.version}).status_code, 403)
        shipment = convert_quote_to_shipment(quote_id=self.approved().pk, actor=self.preparer)
        response = self.client.post(reverse("shipment_update", args=[shipment.pk]), {"quote": shipment.quote_id, "status": "delivered", "record_version": shipment.version})
        self.assertEqual(response.status_code, 200)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, "pending")

    def test_conversion_view_accepts_only_approved_quotes(self):
        self.client.force_login(self.preparer)
        pending = self.quote()
        response = self.client.post(reverse("shipment_create"), {"quote": pending.pk, "status": "pending"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Shipment.objects.exists())
        quote = self.approved()
        self.assertRedirects(self.client.post(reverse("shipment_create"), {"quote": quote.pk, "status": "pending"}), reverse("shipment_list"))
        self.assertEqual(Shipment.objects.get().quote_id, quote.pk)

    def test_failed_cancellation_form_remains_editable(self):
        self.client.force_login(self.preparer)
        shipment = convert_quote_to_shipment(quote_id=self.approved().pk, actor=self.preparer)
        response = self.client.post(reverse("shipment_update", args=[shipment.pk]), {
            "quote": shipment.quote_id, "status": "cancelled", "record_version": shipment.version,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["read_only"])
        self.assertContains(response, "A reason is required")
        self.assertEqual(response.context["workflow_record"].status, "pending")

    def test_shipment_creation_rolls_back_when_auditing_fails(self):
        quote = self.approved()
        with patch("core.signals.AuditRecord.objects.using", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError):
                convert_quote_to_shipment(quote_id=quote.pk, actor=self.preparer)
        self.assertFalse(Shipment.objects.exists())
