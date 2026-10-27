# Commercial operations and expansion

The `finance`, `integrations`, `inventory`, `orders`, `procurement` and `fleet` apps
provide the commercial expansion using Django ORM, service functions, signals,
permission-checked views and shared templates. Requested specialist skills were not
installed locally; this implementation is part of the repository.

## Modules and screens

| App | Workspace | Implemented records and workflows |
| --- | --- | --- |
| finance | `/finance/` | Invoice balances, customer/supplier payments, reversals of unreconciled manual entries, bank statement import, matching, closure, CSV/PDF reports |
| inventory | `/inventory/` | Product catalogue, warehouse CRUD with archival, stock-to-catalogue links, reservations, low-stock alerts and the existing movement ledger |
| orders | `/orders/` | Quote-linked orders and priced lines, submission, Admin approval, reservation, fulfillment, fleet dispatch, delivery-based closure and pre-fulfillment cancellation |
| procurement | `/procurement/` | Suppliers, append-only supplier audits, procurement requests, Admin approvals, purchase orders, partial/idempotent goods receipts and supplier payment linkage |
| fleet | `/fleet/` | Vehicles, drivers/licences, exclusive assignments, manual route/GPS checkpoints, service schedules and maintenance completion |
| integrations | `/integrations/` | Provider configuration, durable Celery queue, retries, readback verification, gateway intents and review/recheck screens |

All staff screens use the orange dashboard shell. Lists support server-side search,
date/status/staff filters, pagination and bounded CSV/PDF exports with audit references.
Date filters use payment dates for payments, statement dates for reconciliation and
creation dates elsewhere. Invalid filter exports return a validation response.
Historical records are retained; archive products/warehouses rather than hard-delete.
Application services guard standard ORM saves, updates, bulk writes and deletes.
These Python guards are not database triggers or protection against privileged SQL.

## Existing records are preserved

`finance.Invoice` is an ORM proxy over the existing `payments.Invoice` table.
`inventory.Warehouse` proxies `organization.Warehouse`. `inventory.StockLevel` links
one product to one existing `operations.InventoryItem`: it does not duplicate the
quantity or ledger. Creating a stock level for an existing warehouse/SKU adopts that
item only when its unit matches. Existing unlinked inventory remains available under
the original Inventory screen; link it to the catalogue to use orders/procurement.
Do not create a second opening-balance movement for adopted stock.

## Approval, stock and dispatch rules

Every customer order, procurement request and purchase order requires a separate
Admin approver, regardless of amount. The preparer cannot self-approve. Existing
quotation pricing thresholds remain UGX 50,000,000 / USD 15,000; this change does not
replace quotation policy. Default role grants are extended by `seed_roles` without
removing deliberate assignments or changing user memberships.

Order line totals and currency must equal the approved quotation. Order creation
locks the quotation against repricing/reassignment. Approval reserves stock under
item locks; legacy manual stock issues cannot consume reserved quantities. Fulfillment
issues each reservation once and creates/reuses the quotation's pending shipment.
Dispatch requires an available vehicle, capacity, a valid driver licence and service
limits not yet due. Existing external-carrier/non-order shipments retain their original
workflow. Shipment dispatch signals synchronize the order; delivery releases fleet.
Closure requires confirmed delivery. Closed/cancelled records cannot be reopened by
editing fields. Issued-stock returns, credit notes and provider refunds need separate
approved business workflows and are not simulated by cancellation or ledger reversal.

Purchasing requires a current passing supplier audit, an approved request, positive
lines within budget and a separate Admin purchase approval. One purchase order is
created per request. `sent` records the team's supplier dispatch; it does not send an
email automatically. Partial receipts cannot exceed ordered quantities. A unique
delivery reference prevents a retry receiving stock twice. Receipts update purchase
status and the canonical inventory ledger atomically. Paid/received purchases cannot
be cancelled. Purchase prices currently have no additional tax calculation; agree
supplier-tax requirements before using this module for statutory accounts.

## Finance and reconciliation

Payment amounts must be positive, match document currency and not exceed the current
outstanding balance. Each payment targets exactly one invoice or approved purchase
order. Idempotency keys and provider/reference uniqueness prevent duplicate postings.
Manual entries record cash/bank receipts or disbursements; they do not instruct a bank
transfer. Only provider verification can post gateway receipts. Manual reversals are
Admin-only and blocked after bank matching; gateway refunds require a future verified
refund workflow. Paid invoices and invoices with unresolved payment intents cannot be
voided. Invoice PDFs include recorded payments and outstanding balances.

Import UTF-8 bank statements (maximum 2 MB / 1,000 rows):

```csv
external_reference,amount,posted_date,description
BANK-RECEIPT-001,100000.00,2026-10-27,Customer receipt
BANK-SUPPLIER-001,-25000.00,2026-10-27,Supplier payment
```

Opening balance plus signed statement movements must equal closing balance. Match
each line to a posted payment with the same external reference, exact amount,
currency and direction. A payment can match only one line. Close reconciliation only
when every line is matched. Reconciliation exports retain statement/payment references.
FX conversion, bank fees, split allocations, statutory numbering and tax reporting
are not inferred from these CSVs; obtain accounting requirements before adding them.

## Provider adapters

**Odoo:** JSON-2 adapter for Odoo 19/20. For a new installation, Odoo 20 Enterprise
Custom is the recommended starting point; Odoo.sh can host custom modules/staging.
Confirm API access and actual model/field availability on the chosen database.
Invoices and approved purchase orders queue automatically when the Odoo connection
is active. Mapped contacts, currencies, taxes, accounts, journals, products and units
are explicit; nothing is guessed from a matching email address. Exports create draft
documents, read back totals/currency and reuse the NASIL external reference on retry.
Local cancellation queues cancellation of remote draft documents; posted Odoo
documents require accountant intervention, not an automatic credit note.
The source status is checked around export to catch cancellation during delivery.
Accounting remains responsible for final posting, taxes and reconciliation in Odoo.

**Flutterwave:** v3 Standard hosted checkout. The server generates the reference,
amount and currency from the invoice. Verification uses the provider API, including
status, amount, currency and reference checks. The `verif-hash` webhook only schedules
verification; neither callback amounts nor browser redirect query parameters post money.

**pawaPay:** v2 mobile-money deposits and authenticated status polling. Deposit UUID
and client reference remain stable. Country-code phone number, configured provider
and supported currency are required. Configure UGX providers for the merchant account;
USD is not silently converted. No unauthenticated callback is trusted. Workers poll
the status API and only completed, matching deposits post receipts.

Customers can pay from an owned issued invoice when enabled providers are configured.
The payment status page shows provider preparation, checkout/mobile-money instructions,
verification, or a staff-review state. An active/review intent prevents starting a
second invoice payment with another provider. Late receipts that no longer match the
outstanding balance retain their provider reference for review instead of over-allocating.
Admin can recheck a reviewed payment after fixing configuration/allocation issues.

Queue publication happens after transaction commit. Jobs have leases, bounded attempts,
backoff, redacted error codes and manual retry screens. Provider network calls run
outside business transactions. Uncertain initiation responses are reviewed and verified
before retrying a financial POST. External delivery is at least once: an Odoo deployment
should enforce uniqueness of NASIL external references for stronger duplicate protection.
No API keys, authorization headers or raw provider response bodies enter audit logs.
HTTPS origins are allowlisted, private resolved IPs and redirects are rejected, TLS is
verified, HTTP calls time out and response sizes are bounded.

## Configuration and startup

Install requirements, migrate and seed roles. Provider delivery defaults to disabled;
no real financial messages or payment instructions are sent by tests.

```bash
python manage.py migrate
python manage.py seed_roles
celery -A backend worker --loglevel=INFO
celery -A backend beat --loglevel=INFO
```

Use supervised Linux workers and one beat scheduler with Redis. Notification and
commercial queues share the existing Celery app. Configure a dedicated active staff
service account with `finance.add_payment` for confirmed gateway postings; do not
use a customer or a superuser merely to bypass setup.

```text
INTEGRATIONS_DELIVERY_ENABLED=false
PUBLIC_SITE_URL=https://your-nasil-domain.example
INTEGRATIONS_SERVICE_USER_ID=YOUR_FINANCE_SERVICE_USER_ID
INTEGRATIONS_ALLOWED_HOSTS=your-company.odoo.com,api.flutterwave.com,api.sandbox.pawapay.io,api.pawapay.io
ODOO_BASE_URL=https://your-company.odoo.com
ODOO_DATABASE=your-database
ODOO_API_KEY=...
FLUTTERWAVE_SECRET_KEY=...
FLUTTERWAVE_WEBHOOK_SECRET=...
PAWAPAY_API_TOKEN=...
PAWAPAY_BASE_URL=https://api.sandbox.pawapay.io
PAWAPAY_CURRENCIES=UGX
PAWAPAY_PROVIDERS=YOUR_ENABLED_MOBILE_MONEY_PROVIDERS
```

Additional JSON maps: `ODOO_CUSTOMER_ID_MAP`, `ODOO_SUPPLIER_ID_MAP`,
`ODOO_CURRENCY_ID_MAP`, `ODOO_PRODUCT_ID_MAP`, `ODOO_UOM_ID_MAP`,
`ODOO_SALES_JOURNAL_ID_MAP`, `ODOO_INCOME_ACCOUNT_ID_MAP`, `ODOO_TAX_ID_MAP`.
Keys are NASIL customer/supplier/product IDs, currency codes or unit names;
tax keys are currency/rate pairs such as `UGX:18.00`. Values are positive Odoo IDs.
Example currency map: `{"UGX": 2, "USD": 3}`. Verify tax inclusion and rounding in
staging: mismatched readback totals stop synchronization. Company-specific mapping
and API keys belong in environment configuration, not committed credentials.

Create provider connections under Integration hub using codes `odoo`, `flutterwave`
or `pawapay`; use the exact credential environment names above. Odoo type is
`accounting`; gateway types are `payment_gateway`. Flutterwave origin is
`https://api.flutterwave.com`; pawaPay defaults to sandbox. Register the Flutterwave
callback at `/integrations/webhooks/flutterwave/`. Django does not load `.env` automatically.

## Django examples

```python
from finance.models import Invoice, Payment, Reconciliation
from orders.services import save_order, add_line, transition_order
from procurement.services import receive_goods

order = save_order(actor=preparer, data={"quote": approved_quote, "notes": ""})
add_line(actor=preparer, record_id=order.pk, stock=stock, quantity_value=5,
         unit_price=unit_price)
transition_order(actor=preparer, record_id=order.pk, target="submitted")
transition_order(actor=other_admin, record_id=order.pk, target="approved")
transition_order(actor=warehouse_staff, record_id=order.pk, target="fulfilled")
# Assign fleet, then dispatch; the existing shipment transition services are reused.
transition_order(actor=dispatcher, record_id=order.pk, target="shipped")

receive_goods(actor=warehouse_staff, record_id=purchase.pk, line=purchase_line,
              quantity_value=2, delivery_reference="SUPPLIER-NOTE-001")
```

Reusable validation lives in `operations/commercial.py`, `core/business_rules.py`
and module services. Shared UI lives in `operations/module_ui.py` and
`templates/expansion/`; each app owns its models, forms, services and URLs.
`integrations/adapters.py` and `http.py` separate provider protocols from workflows.
Internal functions can be reused from future APIs instead of bypassing state rules.

## Acceptance and live setup

Local verification on 27 October 2026: full Django suite ran 183 tests, with 179
passing and four PostgreSQL-only tests skipped on SQLite. System checks and migration
consistency checks passed. Browser QA used a separate database for product creation,
commercial lists/details and mobile layouts; report PDFs were rendered and inspected.
The create-form empty-version regression is covered by a dedicated test.

The local database was backed up before migration; all original columns/rows in 31
existing data tables were preserved, with integrity and foreign-key checks passing.
QA fixtures and screenshots are isolated under ignored `output/`; no provider
messages, financial transactions or live accounting writes were sent.

Run all tests against an isolated PostgreSQL database before deployment. SQLite
cannot establish production row-lock/concurrency guarantees. Provider tests mock HTTP;
live Odoo databases, credentials, account mappings, merchant capabilities, callbacks,
Redis/workers and provider sandbox transactions must be configured and verified before
enabling traffic. Automated GPS telemetry, financial refunds, multi-bank reconciliation,
FX and statutory account/tax localization remain separate extensions.

References: [Odoo JSON-2](https://www.odoo.com/documentation/19.0/developer/misc/api/external_api.html),
[Odoo supported versions](https://www.odoo.com/documentation/20.0/administration/supported_versions.html),
[Odoo plans](https://www.odoo.com/pricing),
[Flutterwave Standard](https://developer.flutterwave.com/docs/flutterwave-standard-1),
[Flutterwave verification](https://developer.flutterwave.com/reference/verify-transaction-with-tx_ref),
[Flutterwave webhooks](https://developer.flutterwave.com/v3.0.0/docs/webhooks),
[pawaPay deposits](https://docs.pawapay.io/v2/api-reference/deposits/initiate-deposit),
[pawaPay status API](https://docs.pawapay.io/v2/api-reference/deposits/check-deposit-status).
