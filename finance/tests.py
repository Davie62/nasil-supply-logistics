"""Regression suite for the payment ledger, reversals, statements and reconciliation."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from core.test_commercial_fixtures import CommercialFixtureMixin
from core.test_helpers import booked_shipment
from finance.models import Payment
from finance.services import (
    balance_due,
    close_reconciliation,
    import_statement,
    match_payment,
    paid_total,
    record_payment,
    reverse_payment,
    save_payment,
)
from payments.services import issue_invoice, void_invoice
from procurement.services import (
    add_purchase_line,
    audit_supplier,
    save_purchase_order,
    save_request,
    save_supplier,
    transition_purchase,
    transition_request,
)


class FinanceTests(CommercialFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self._sequence = 0

    def next_sequence(self):
        self._sequence += 1
        return self._sequence

    def make_invoice(self, quote=None):
        quote = quote or booked_shipment(self.customer).quote
        return issue_invoice(
            actor=self.maker, quote_id=quote.pk,
            due_date=timezone.localdate() + timedelta(days=30),
        )

    def make_supplier(self):
        sequence = self.next_sequence()
        supplier = save_supplier(actor=self.maker, data={
            "name": f"Finance supplier {sequence}",
            "registration_number": f"FIN-SUP-{sequence:03d}",
            "email": f"finance-supplier-{sequence}@example.com", "phone": "0",
            "address": "Kampala", "is_active": True,
        })
        audit_supplier(
            actor=self.maker, record_id=supplier.pk, outcome="pass",
            valid_until=timezone.localdate() + timedelta(days=30), notes="Verified",
        )
        return supplier

    def make_purchase_order(self, quantity=10, unit_price=20):
        request = save_request(actor=self.maker, data={
            "purpose": "Stock replenishment", "currency": "UGX",
            "budget": 500, "order": None,
        })
        transition_request(actor=self.maker, record_id=request.pk, target="submitted")
        transition_request(actor=self.approver, record_id=request.pk, target="approved")
        purchase = save_purchase_order(actor=self.maker, data={
            "request": request, "supplier": self.make_supplier(),
        })
        add_purchase_line(
            actor=self.maker, record_id=purchase.pk, stock=self.stock,
            quantity_value=quantity, unit_price=unit_price,
        )
        transition_purchase(actor=self.maker, record_id=purchase.pk, target="submitted")
        transition_purchase(actor=self.approver, record_id=purchase.pk, target="approved")
        return transition_purchase(actor=self.maker, record_id=purchase.pk, target="sent")

    def pay_invoice(self, invoice=None, amount=None, currency=None, method="bank",
                    reference=None, key=None, provider="manual", paid_at=None):
        invoice = invoice or self.make_invoice()
        sequence = self.next_sequence()
        return record_payment(
            actor=self.maker, invoice=invoice,
            amount=amount if amount is not None else invoice.amount,
            currency=currency or invoice.currency, method=method,
            external_reference=reference or f"PAY-{sequence:03d}",
            idempotency_key=key or f"key-{sequence:03d}", provider=provider,
            paid_at=paid_at,
        )

    def statement(self, rows, header="external_reference,amount,posted_date,description"):
        body = header + "\n" + "\n".join(rows) + "\n"
        return SimpleUploadedFile("statement.csv", body.encode("utf-8"), content_type="text/csv")

    def import_reconciliation(self, rows, number="REC-001", currency="UGX",
                              opening="0", closing=None, statement_date=None):
        if closing is None:
            closing = str(sum(Decimal(row.split(",")[1]) for row in rows))
        return import_statement(
            actor=self.maker, number=number, currency=currency,
            statement_date=statement_date or timezone.localdate(),
            opening_balance=opening, closing_balance=closing,
            csv_file=self.statement(rows),
        )

    def test_payment_requires_exactly_one_document(self):
        invoice = self.make_invoice()
        with self.assertRaisesMessage(ValidationError, "exactly one"):
            record_payment(
                actor=self.maker, amount=1, currency="UGX", method="bank",
                external_reference="NONE", idempotency_key="none",
            )
        with self.assertRaisesMessage(ValidationError, "exactly one"):
            record_payment(
                actor=self.maker, invoice=invoice, purchase_order=invoice, amount=1,
                currency="UGX", method="bank", external_reference="BOTH",
                idempotency_key="both",
            )

    def test_payment_validates_currency_balance_method_and_dates(self):
        invoice = self.make_invoice()
        with self.assertRaisesMessage(ValidationError, "currency must match"):
            self.pay_invoice(invoice=invoice, currency="USD")
        with self.assertRaisesMessage(ValidationError, "outstanding balance"):
            self.pay_invoice(invoice=invoice, amount=invoice.amount + 1)
        with self.assertRaisesMessage(ValidationError, "future"):
            self.pay_invoice(invoice=invoice, paid_at=timezone.now() + timedelta(days=1))
        with self.assertRaisesMessage(ValidationError, "Gateway payments must be confirmed"):
            self.pay_invoice(invoice=invoice, method="gateway", provider="manual")
        with self.assertRaisesMessage(ValidationError, "required"):
            self.pay_invoice(invoice=invoice, reference="   ")
        with self.assertRaisesMessage(ValidationError, "at least 0.01"):
            self.pay_invoice(invoice=invoice, amount=0)

        void_invoice(actor=self.maker, invoice_id=invoice.pk, reason="Billing error")
        with self.assertRaisesMessage(ValidationError, "Voided invoices cannot receive payments"):
            self.pay_invoice(invoice=invoice)

    def test_supplier_payments_require_an_approved_order(self):
        request = save_request(actor=self.maker, data={
            "purpose": "Stock replenishment", "currency": "UGX",
            "budget": 500, "order": None,
        })
        transition_request(actor=self.maker, record_id=request.pk, target="submitted")
        transition_request(actor=self.approver, record_id=request.pk, target="approved")
        draft = save_purchase_order(actor=self.maker, data={
            "request": request, "supplier": self.make_supplier(),
        })
        add_purchase_line(
            actor=self.maker, record_id=draft.pk, stock=self.stock,
            quantity_value=10, unit_price=20,
        )
        with self.assertRaisesMessage(ValidationError, "approved purchase order"):
            record_payment(
                actor=self.maker, purchase_order=draft, amount=200, currency="UGX",
                method="bank", external_reference="DRAFT-PO", idempotency_key="draft-po",
            )

    def test_payment_idempotency_and_unique_provider_reference(self):
        invoice = self.make_invoice()
        first = self.pay_invoice(invoice=invoice, reference="REF-1", key="key-1")
        second = self.pay_invoice(invoice=invoice, reference="REF-1", key="key-1")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.count(), 1)

        with self.assertRaisesMessage(ValidationError, "already used for a different payment"):
            self.pay_invoice(invoice=invoice, amount=invoice.amount - 1, reference="REF-1", key="key-1")

        with self.assertRaises(ValidationError):
            self.pay_invoice(invoice=self.make_invoice(), reference="REF-1", key="key-2")

    def test_posted_payments_are_immutable(self):
        payment = self.pay_invoice()
        with self.assertRaisesMessage(ValidationError, "immutable"):
            save_payment(actor=self.maker, data={"amount": 1}, record_id=payment.pk)
        with self.assertRaises(ValidationError):
            Payment.objects.filter(pk=payment.pk).update(amount=Decimal("1.00"))
        payment.amount = Decimal("1.00")
        with self.assertRaises(ValidationError):
            payment.save()

    def test_reversal_requires_admin_permission_reason_and_unmatched_non_gateway(self):
        payment = self.pay_invoice()
        with self.assertRaises(PermissionDenied):
            reverse_payment(actor=self.maker, record_id=payment.pk, reason="Wrong entry")
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            reverse_payment(actor=self.approver, record_id=payment.pk, reason="  ")

        gateway = self.pay_invoice(
            invoice=self.make_invoice(), method="gateway",
            provider="flutterwave", reference="GW-1", key="gw-1",
        )
        with self.assertRaisesMessage(ValidationError, "Gateway receipts require"):
            reverse_payment(actor=self.approver, record_id=gateway.pk, reason="Refund")

        reconciled = self.pay_invoice(
            invoice=self.make_invoice(), reference="MATCH-REV", key="match-rev",
        )
        reconciliation = self.import_reconciliation([(
            f"{reconciled.external_reference},{reconciled.amount},"
            f"{timezone.localdate().isoformat()},Payment"
        )])
        match_payment(
            actor=self.maker, record_id=reconciliation.pk,
            line=reconciliation.lines.get(), payment=reconciled,
        )
        with self.assertRaisesMessage(ValidationError, "matched statement payments"):
            reverse_payment(actor=self.approver, record_id=reconciled.pk, reason="Matched")

        reversible = self.pay_invoice(
            invoice=self.make_invoice(), reference="REV-1", key="rev-1",
        )
        reversed_payment = reverse_payment(
            actor=self.approver, record_id=reversible.pk, reason="Duplicate entry",
        )
        self.assertEqual(reversed_payment.status, "reversed")
        self.assertIsNotNone(reversed_payment.reversed_at)
        self.assertEqual(reversed_payment.reversal_reason, "Duplicate entry")
        with self.assertRaisesMessage(ValidationError, "Only posted payments"):
            reverse_payment(actor=self.approver, record_id=reversible.pk, reason="Again")

    def test_balance_tracks_posted_and_reversed_payments(self):
        invoice = self.make_invoice()
        self.assertEqual(balance_due(invoice), invoice.amount)

        payment = self.pay_invoice(invoice=invoice)
        self.assertEqual(paid_total(invoice), invoice.amount)
        self.assertEqual(balance_due(invoice), Decimal("0.00"))

        reverse_payment(actor=self.approver, record_id=payment.pk, reason="Duplicate entry")
        self.assertEqual(paid_total(invoice), Decimal("0.00"))
        self.assertEqual(balance_due(invoice), invoice.amount)

    def test_statement_import_validates_csv_structure_and_balances(self):
        today = timezone.localdate().isoformat()
        with self.assertRaisesMessage(ValidationError, "statement CSV header"):
            import_statement(
                actor=self.maker, number="REC-BAD-HEADER", currency="UGX",
                statement_date=timezone.localdate(), opening_balance="0",
                closing_balance="10",
                csv_file=self.statement(
                    [f"REF-1,10,{today},Payment"],
                    header="reference,amount,posted_date,description",
                ),
            )
        with self.assertRaisesMessage(ValidationError, "ISO dates"):
            self.import_reconciliation([f"REF-1,10,not-a-date,Payment"])
        with self.assertRaisesMessage(ValidationError, "ISO dates"):
            self.import_reconciliation([f"REF-1,0.00,{today},Payment"])
        with self.assertRaisesMessage(ValidationError, "opening balance plus net movements"):
            self.import_reconciliation(
                [f"REF-1,10,{today},First", f"REF-1,20,{today},Duplicate"],
            )
        with self.assertRaisesMessage(ValidationError, "opening balance plus net movements"):
            self.import_reconciliation([f"REF-1,10,{today},Payment"], closing="999")
        with self.assertRaises(ValidationError):
            self.import_reconciliation(
                [f"REF-1,10,{today},Payment"],
                statement_date=timezone.localdate() - timedelta(days=1),
            )
        with self.assertRaisesMessage(ValidationError, "2 MB"):
            import_statement(
                actor=self.maker, number="REC-BIG", currency="UGX",
                statement_date=timezone.localdate(), opening_balance="0",
                closing_balance="0",
                csv_file=SimpleUploadedFile(
                    "big.csv", b"x" * (2 * 1024 * 1024 + 1), content_type="text/csv",
                ),
            )

        reconciliation = self.import_reconciliation(
            [f"REF-1,10,{today},First", f"REF-2,20,{today},Second"],
        )
        self.assertEqual(reconciliation.lines.count(), 2)
        self.assertEqual(
            set(reconciliation.lines.values_list("external_reference", flat=True)),
            {"REF-1", "REF-2"},
        )

    def test_statement_matching_requires_reference_amount_currency_and_direction(self):
        invoice = self.make_invoice()
        payment = self.pay_invoice(invoice=invoice, reference="MATCH-1", key="match-1")
        today = timezone.localdate().isoformat()
        reconciliation = self.import_reconciliation([(
            f"{payment.external_reference},{payment.amount},{today},Payment"
        )])
        line = reconciliation.lines.get()

        other = self.pay_invoice(
            invoice=self.make_invoice(), reference="OTHER-1", key="other-1",
        )
        with self.assertRaisesMessage(ValidationError, "same reference"):
            match_payment(actor=self.maker, record_id=reconciliation.pk, line=line, payment=other)

        wrong_amount = self.import_reconciliation(
            [f"{payment.external_reference},{payment.amount - 1},{today},Payment"],
            number="REC-AMOUNT",
        )
        with self.assertRaisesMessage(ValidationError, "same reference"):
            match_payment(
                actor=self.maker, record_id=wrong_amount.pk,
                line=wrong_amount.lines.get(), payment=payment,
            )

        purchase = self.make_purchase_order()
        purchase_payment = record_payment(
            actor=self.maker, purchase_order=purchase, amount=purchase.total,
            currency="UGX", method="bank", external_reference="PO-MATCH",
            idempotency_key="po-match",
        )
        direction = self.import_reconciliation(
            [f"{purchase_payment.external_reference},{purchase_payment.amount},{today},Supplier"],
            number="REC-DIRECTION",
        )
        with self.assertRaisesMessage(ValidationError, "same reference"):
            match_payment(
                actor=self.maker, record_id=direction.pk,
                line=direction.lines.get(), payment=purchase_payment,
            )

        matched = match_payment(
            actor=self.maker, record_id=reconciliation.pk, line=line, payment=payment,
        )
        line.refresh_from_db()
        self.assertEqual(line.payment_id, payment.pk)
        self.assertEqual(matched.status, "open")

        duplicate = self.import_reconciliation(
            [f"{payment.external_reference},{payment.amount},{today},Duplicate"],
            number="REC-DUPLICATE",
        )
        with self.assertRaisesMessage(ValidationError, "already reconciled"):
            match_payment(
                actor=self.maker, record_id=duplicate.pk,
                line=duplicate.lines.get(), payment=payment,
            )

        reversed_payment = self.pay_invoice(
            invoice=self.make_invoice(), reference="REVERSED-1", key="reversed-1",
        )
        reverse_payment(actor=self.approver, record_id=reversed_payment.pk, reason="Duplicate")
        reversed_recon = self.import_reconciliation(
            [f"{reversed_payment.external_reference},{reversed_payment.amount},{today},Reversed"],
            number="REC-REVERSED",
        )
        with self.assertRaisesMessage(ValidationError, "posted payment"):
            match_payment(
                actor=self.maker, record_id=reversed_recon.pk,
                line=reversed_recon.lines.get(), payment=reversed_payment,
            )

    def test_close_reconciliation_requires_every_line_matched(self):
        today = timezone.localdate().isoformat()
        first = self.pay_invoice(invoice=self.make_invoice(), reference="CLOSE-1", key="close-1")
        second = self.pay_invoice(invoice=self.make_invoice(), reference="CLOSE-2", key="close-2")
        reconciliation = self.import_reconciliation([
            f"{first.external_reference},{first.amount},{today},First",
            f"{second.external_reference},{second.amount},{today},Second",
        ])
        lines = list(reconciliation.lines.order_by("external_reference"))
        match_payment(actor=self.maker, record_id=reconciliation.pk, line=lines[0], payment=first)

        with self.assertRaisesMessage(ValidationError, "Match all statement lines"):
            close_reconciliation(actor=self.maker, record_id=reconciliation.pk)

        match_payment(actor=self.maker, record_id=reconciliation.pk, line=lines[1], payment=second)
        closed = close_reconciliation(actor=self.maker, record_id=reconciliation.pk)
        self.assertEqual(closed.status, "closed")
        self.assertIsNotNone(closed.closed_at)
        with self.assertRaisesMessage(ValidationError, "Match all statement lines"):
            close_reconciliation(actor=self.maker, record_id=reconciliation.pk)

    def test_closed_reconciliation_rejects_further_matches(self):
        today = timezone.localdate().isoformat()
        payment = self.pay_invoice(invoice=self.make_invoice(), reference="LOCK-1", key="lock-1")
        reconciliation = self.import_reconciliation([(
            f"{payment.external_reference},{payment.amount},{today},Payment"
        )])
        line = reconciliation.lines.get()
        match_payment(actor=self.maker, record_id=reconciliation.pk, line=line, payment=payment)
        close_reconciliation(actor=self.maker, record_id=reconciliation.pk)

        other = self.pay_invoice(invoice=self.make_invoice(), reference="LOCK-2", key="lock-2")
        with self.assertRaisesMessage(ValidationError, "open line"):
            match_payment(actor=self.maker, record_id=reconciliation.pk, line=line, payment=other)

    def test_finance_services_reject_unprivileged_staff(self):
        invoice = self.make_invoice()
        with self.assertRaises(PermissionDenied):
            record_payment(
                actor=self.outsider, invoice=invoice, amount=1, currency=invoice.currency,
                method="bank", external_reference="DENIED", idempotency_key="denied",
            )
        with self.assertRaises(PermissionDenied):
            import_statement(
                actor=self.outsider, number="REC-DENIED", currency="UGX",
                statement_date=timezone.localdate(), opening_balance="0",
                closing_balance="0", csv_file=self.statement([]),
            )
        payment = self.pay_invoice(invoice=invoice, reference="PERM-1", key="perm-1")
        reconciliation = self.import_reconciliation([(
            f"{payment.external_reference},{payment.amount},"
            f"{timezone.localdate().isoformat()},Payment"
        )], number="REC-PERM")
        line = reconciliation.lines.get()
        with self.assertRaises(PermissionDenied):
            match_payment(actor=self.outsider, record_id=reconciliation.pk, line=line, payment=payment)
        with self.assertRaises(PermissionDenied):
            close_reconciliation(actor=self.outsider, record_id=reconciliation.pk)
        with self.assertRaises(PermissionDenied):
            reverse_payment(actor=self.outsider, record_id=payment.pk, reason="Denied")
