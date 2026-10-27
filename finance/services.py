import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from core.business_rules import require_permission, validate_version, decimal_value
from operations.commercial import persist, money
from payments.models import Invoice
from .models import Payment, Reconciliation, StatementLine


def paid_total(document):
    payments = document.finance_payments if isinstance(document, Invoice) else document.payments
    return payments.filter(status="posted").aggregate(value=Sum("amount"))["value"] or Decimal("0.00")


def balance_due(document):
    return (document.amount if isinstance(document, Invoice) else document.total) - paid_total(document)


@transaction.atomic
def record_payment(*, actor, invoice=None, purchase_order=None, amount, currency, method, external_reference, idempotency_key, paid_at=None, provider="manual"):
    require_permission(actor, "finance.add_payment")
    if bool(invoice) == bool(purchase_order):
        raise ValidationError("Choose exactly one customer invoice or supplier purchase order.")
    amount = money(amount)
    if method == "gateway" and provider not in {"flutterwave", "pawapay"}:
        raise ValidationError("Gateway payments must be confirmed through the provider verification workflow.")
    if not external_reference.strip() or not idempotency_key.strip() or method not in {"cash", "bank", "gateway"}:
        raise ValidationError("Payment method, external reference and idempotency key are required.")
    if invoice:
        document = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if document.status != "issued":
            raise ValidationError("Voided invoices cannot receive payments.")
    else:
        from procurement.models import PurchaseOrder
        document = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
        if document.status not in {"approved", "sent", "partially_received", "received"}:
            raise ValidationError("Supplier payments require an approved purchase order.")
    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if (existing.invoice_id, existing.purchase_order_id, existing.amount, existing.currency, existing.external_reference, existing.provider, existing.method) != (
            invoice.pk if invoice else None, purchase_order.pk if purchase_order else None, amount, currency, external_reference, provider, method):
            raise ValidationError("Idempotency key was already used for a different payment.")
        return existing
    if currency != document.currency or amount > balance_due(document):
        raise ValidationError("Payment currency must match the document and amount cannot exceed its outstanding balance.")
    paid_at = paid_at or timezone.now()
    if paid_at > timezone.now():
        raise ValidationError("Payments cannot be dated in the future.")
    payment = Payment(invoice=document if invoice else None, purchase_order=document if purchase_order else None,
        amount=amount, currency=currency, method=method, external_reference=external_reference.strip(), provider=provider,
        idempotency_key=idempotency_key, paid_at=paid_at, recorded_by=actor)
    return persist(payment, actor, "payment_posted", amount=str(amount), currency=currency)


def save_payment(*, actor, data, record_id=None, expected_version=None):
    if record_id:
        raise ValidationError("Posted payments are immutable; reverse an unreconciled payment instead.")
    return record_payment(actor=actor, **data)


@transaction.atomic
def reverse_payment(*, actor, record_id, reason, expected_version=None):
    require_permission(actor, "finance.reverse_payment")
    from operations.services import require_admin
    require_admin(actor)
    original = Payment.objects.get(pk=record_id)
    if original.invoice_id:
        Invoice.objects.select_for_update().get(pk=original.invoice_id)
    else:
        from procurement.models import PurchaseOrder
        PurchaseOrder.objects.select_for_update().get(pk=original.purchase_order_id)
    payment = Payment.objects.select_for_update().get(pk=record_id)
    validate_version(payment, expected_version)
    if not reason.strip() or StatementLine.objects.filter(payment=payment).exists():
        raise ValidationError("A reason is required; matched statement payments cannot be reversed.")
    if payment.method == "gateway":
        raise ValidationError("Gateway receipts require a verified provider refund workflow; a ledger reversal is not a refund.")
    if payment.status != "posted":
        raise ValidationError("Only posted payments can be reversed.")
    payment.status, payment.reversal_reason, payment.reversed_at = "reversed", reason.strip(), timezone.now()
    return persist(payment, actor, "payment_reversed", reason=reason)


def signed_money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) > Decimal("9999999999999.99") or amount != amount.quantize(Decimal(".01")):
            raise ValueError
    except Exception:
        raise ValidationError("Statement values must be finite amounts with up to two decimals.")
    return amount


@transaction.atomic
def import_statement(*, actor, number, currency, statement_date, opening_balance, closing_balance, csv_file):
    require_permission(actor, "finance.add_reconciliation")
    if csv_file.size > 2 * 1024 * 1024:
        raise ValidationError("Statements must be CSV files no larger than 2 MB.")
    try:
        reader = csv.DictReader(StringIO(csv_file.read().decode("utf-8-sig")))
        if set(reader.fieldnames or []) != {"external_reference", "amount", "posted_date", "description"}:
            raise ValueError
        rows = []
        for index, row in enumerate(reader):
            if index >= 1000:
                raise ValueError
            amount = signed_money(row["amount"])
            posted_date = date.fromisoformat(row["posted_date"])
            if not row["external_reference"].strip() or not amount or posted_date > statement_date:
                raise ValueError
            rows.append({"external_reference": row["external_reference"].strip(), "amount": amount, "posted_date": posted_date, "description": row["description"]})
    except (ValueError, UnicodeError, KeyError, TypeError, csv.Error):
        raise ValidationError("Use the statement CSV header external_reference,amount,posted_date,description with ISO dates and up to 1,000 valid rows.")
    opening, closing = signed_money(opening_balance), signed_money(closing_balance)
    if not rows or opening + sum(row["amount"] for row in rows) != closing or len({row["external_reference"] for row in rows}) != len(rows):
        raise ValidationError("Statement references must be unique and opening balance plus net movements must equal closing balance.")
    reconciliation = persist(Reconciliation(number=number, currency=currency, statement_date=statement_date, opening_balance=opening, closing_balance=closing, created_by=actor), actor, "statement_imported")
    for row in rows:
        persist(StatementLine(reconciliation=reconciliation, **row), actor, "statement_line_imported")
    return reconciliation


@transaction.atomic
def match_payment(*, actor, record_id, line, payment, expected_version=None):
    require_permission(actor, "finance.change_reconciliation")
    reconciliation = Reconciliation.objects.select_for_update().get(pk=record_id)
    validate_version(reconciliation, expected_version)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    line = StatementLine.objects.select_for_update().get(pk=line.pk, reconciliation=reconciliation)
    if line.payment_id == payment.pk:
        return reconciliation
    expected_amount = payment.amount if payment.invoice_id else -payment.amount
    if reconciliation.status != "open" or line.payment_id or payment.status != "posted" or payment.currency != reconciliation.currency or line.amount != expected_amount or line.external_reference != payment.external_reference:
        raise ValidationError("Match an open line to a posted payment with the same reference, currency, direction and exact amount.")
    if StatementLine.objects.filter(payment=payment).exists():
        raise ValidationError("This payment is already reconciled.")
    line.payment, line.matched_by, line.matched_at = payment, actor, timezone.now()
    persist(line, actor, "statement_matched", payment=str(payment.reference))
    return persist(reconciliation, actor, "reconciliation_updated")


@transaction.atomic
def close_reconciliation(*, actor, record_id, expected_version=None):
    require_permission(actor, "finance.change_reconciliation")
    reconciliation = Reconciliation.objects.select_for_update().get(pk=record_id)
    validate_version(reconciliation, expected_version)
    if reconciliation.status != "open" or not reconciliation.lines.exists() or reconciliation.lines.filter(payment__isnull=True).exists():
        raise ValidationError("Match all statement lines before closing reconciliation.")
    reconciliation.status, reconciliation.closed_at = "closed", timezone.now()
    return persist(reconciliation, actor, "reconciliation_closed")
