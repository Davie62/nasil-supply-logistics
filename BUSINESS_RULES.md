# Core business rules

## Policy

By default, local quotations use **UGX** and international quotations use **USD**. Currency is derived from `trade_type` and the administrator's current currency policy, never accepted as an editable price input. Existing quotations retain their currency unless their trade scope changes.

NASIL's configured approval limits are **UGX 50,000,000.00** and **USD 15,000.00**, measured against the final total including tax. An authorized approver may approve at or below the limit. Above the limit, the approver must be a superuser or belong to the `Administrator` group, and hold both `approve_quote` and `approve_high_value_quote` permissions. No exchange-rate conversion is performed.

The original creator and latest preparer cannot approve their own quotation, including administrators. Staff who price an anonymous request become its preparer. A second authorized person is required.

Override the policy through an environment variable (Django does not load `.env` automatically):

```bash
export QUOTATION_APPROVAL_THRESHOLDS='{"UGX":"50000000.00","USD":"15000.00"}'
```

Missing, negative or invalid currency limits block approval. The environment policy is the fallback before the first database settings save; afterward the audited settings singleton is authoritative and changes apply immediately. See INTERNAL_OPERATIONS.md. Prior approvals are not retrospectively revoked when a limit changes.

## Django schemas

The executable ORM models live in `quotations/models.py`, `shipments/models.py`, and `core/models.py`.

| Model | Fields and guarantees |
| --- | --- |
| `Quote` | Customer, route, service, cargo and positive weight; local/international scope; currency; base price, weight rate, surcharge, discount, tax percentage; calculated subtotal/tax/total; validity date; status; creator, preparer, approver and approval timestamp; creation/update timestamps and version. |
| `Shipment` | Unique tracking number; protected one-to-one quotation; carrier, current location and ETA; pending/in-transit/delivered/cancelled status; dispatch, delivery and cancellation timestamps; creator and version. |
| `AuditRecord` | Protected quotation/shipment links; actor plus retained username snapshot; action, previous/new statuses, reason, changed-field before/after JSON, object version and event timestamp. `shipment.history` exposes all shipment events; `quote.audit_records` includes quotation and linked conversion/shipment events. |

Database checks enforce positive weight, nonnegative cargo value and monetary inputs, tax between 0 and 100, known statuses and supported scope/currency codes. Business authorization and cross-record approval rules are enforced by the workflow functions.

Example excerpts from the implemented Django models (remaining fields and constraints are in the source files):

```python
class Quote(WorkflowModel):
    base_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)

class Shipment(WorkflowModel):
    quote = models.OneToOneField("quotations.Quote", on_delete=models.PROTECT,
                                 related_name="shipment")
    dispatched_at = models.DateTimeField(null=True, blank=True, editable=False)
    delivered_at = models.DateTimeField(null=True, blank=True, editable=False)

class AuditRecord(models.Model):
    shipment = models.ForeignKey("shipments.Shipment", on_delete=models.PROTECT,
                                  null=True, blank=True, related_name="history")
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
```

Pricing is aggregate pricing rather than a line-item/invoice ledger:

```python
subtotal = round_money(base_amount + weight * rate_per_kg + surcharge - discount)
tax_amount = round_money(subtotal * tax_rate / 100)
total_amount = subtotal + tax_amount
```

`round_money` uses Decimal with ROUND_HALF_UP to two decimal places. Cargo value is the declared value of the goods, separate from freight pricing. No tax rate is assumed: authorized preparers supply the applicable rate.

## Workflows and examples

Quotation transitions:

```text
pending -> reviewed -> approved
pending/reviewed -> rejected -> pending
reviewed -> pending
approved -> reviewed (reason required; clears approval; only before conversion)
```

Approval requires a positive price, a validity date of today or later, configured policy, and a different authorized approver. Approved terms cannot be edited. Converted quotations cannot be edited or reopened.

```python
from decimal import Decimal
from django.utils import timezone
from quotations.workflows import create_quote, transition_quote
from shipments.workflows import convert_quote_to_shipment, transition_shipment

quote = create_quote(actor=sales_user, data={
    "customer": customer,
    "pickup_location": "Kampala",
    "destination": "Jinja",
    "cargo_description": "Packaged goods",
    "weight": Decimal("250.00"),
    "trade_type": "local",  # UGX; international derives USD
    "base_amount": Decimal("100000.00"),
    "rate_per_kg": Decimal("500.00"),
    "tax_rate": Decimal("0.00"),
    "valid_until": timezone.localdate(),
})
quote = transition_quote(quote_id=quote.pk, actor=sales_user,
                         target="reviewed", expected_version=quote.version)
quote = transition_quote(quote_id=quote.pk, actor=approver_user,
                         target="approved", expected_version=quote.version)
shipment = convert_quote_to_shipment(quote_id=quote.pk, actor=dispatcher_user)
shipment = transition_shipment(shipment_id=shipment.pk, actor=dispatcher_user,
                               target="in_transit", expected_version=shipment.version)
shipment = transition_shipment(shipment_id=shipment.pk, actor=dispatcher_user,
                               target="delivered", expected_version=shipment.version)
```

Shipment transitions are `pending -> in_transit -> delivered`, or `pending/in_transit -> cancelled` with a reason. Delivered/cancelled shipments are locked. New ETAs cannot be in the past; an existing overdue ETA can remain unchanged when progressing a shipment. Quotes cannot be swapped after booking.

Conversion requires shipment creation and quotation viewing permissions, an approved unexpired quotation and verified approval metadata. It locks the quotation and uses a one-to-one relation to prevent duplicate bookings. Retrying conversion returns the existing shipment without another audit event or applying changed booking parameters.

Reusable validation is in `core/business_rules.py`:

```python
from core.business_rules import (
    SHIPMENT_TRANSITIONS, calculate_price, validate_transition,
)

validate_transition("pending", "in_transit", SHIPMENT_TRANSITIONS)
subtotal, tax, total = calculate_price(
    weight="250.00", base_amount="100000.00", rate_per_kg="500.00",
    surcharge="0.00", discount="0.00", tax_rate="0.00",
)
```

## Views, signals and write boundaries

Existing quotation edit pages expose separate CSRF-protected status actions and audit history. The shipment creation page converts approved quotes; its quote selector excludes expired/unapproved/already-booked records. Shipment edit forms show only legal next statuses. Approval-only staff can use the quotation status workflow without editing commercial terms. Hidden versions reject stale browser edits.

Services use `transaction.atomic()` and PostgreSQL `select_for_update()` locks. Core pre-save/post-save signals record changed fields synchronously inside the same transaction; audit failure rolls back the business write. Quote/shipment admin pages are read-only to keep admin saves from bypassing workflows. `seed_roles` gives ordinary approval to Administrator, Operations Manager and Finance Officer; only Administrator gets high-value permission.

Normal model saves and bulk queryset writes are guarded. Anonymous requests may create unpriced pending quotes, with actor labelled `Public / system`. All staff updates must use workflows. Do not use `save_base`, `_base_manager`, raw SQL, fixtures with raw saves, or external database tools for business changes: these are privileged escape hatches outside application authorization and auditing. Audit records reject normal updates/deletes; they are not a cryptographically signed or database-administrator-proof ledger.

SQLite is suitable for local functional testing but does not supply PostgreSQL row locks. Concurrent conversion/edit tests are skipped where row locking is unsupported and must pass on PostgreSQL before production.

## Migration and rollout

1. Back up the database, run `python manage.py migrate`, then `python manage.py seed_roles`.
2. Assign users to the intended groups. Ensure at least two staff can prepare/approve; the preparer cannot self-approve.
3. Review legacy quotations: they retain their status, have no invented prices or approval actors, and receive a `legacy_snapshot` event. Old `approved` labels alone do not authorize conversion. Before booking an unconverted legacy quotation, reopen it, set scope/pricing/validity, and approve through the new workflow.
4. Existing shipments remain intact. Historical dispatch/delivery timestamps remain null when unknown; the migration does not fabricate history. Their state at rollout is recorded as a snapshot.

Legacy quotations default to local/UGX for the new, zero-valued freight pricing fields; staff must select the correct scope when preparing them. Migration preflight refuses invalid legacy weights, cargo values or statuses rather than silently rewriting business records. New settings do not automatically deploy to another host.

References: [Django transactions](https://docs.djangoproject.com/en/6.0/topics/db/transactions/), [model validation](https://docs.djangoproject.com/en/6.0/ref/models/instances/#validating-objects), and [row locking](https://docs.djangoproject.com/en/6.0/ref/models/querysets/#select-for-update).
