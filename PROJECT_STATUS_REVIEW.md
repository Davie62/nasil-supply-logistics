# NASIL project structure, architecture and implementation review

Review date: **14 November 2026**. Scope: the current working tree, including
uncommitted security and mobile changes. This is a repository-grounded status
review; live provider accounts, remote CI, hosting health and production configuration
were not inspected. "Implemented" means executable models, services and relevant
routes/templates exist; it does not mean production acceptance is complete.

## 1. Overall assessment

NASIL is a substantial **modular Django monolith** with 18 local apps. The core
quotation-to-shipment workflow, internal operations, customer portal and commercial
modules are implemented. The main remaining work is release consistency, verified
production operations, live integration acceptance and business extensions.

There is no basis for a reliable percentage-complete estimate: the business scope,
acceptance criteria and production checks do not have a complete signed-off baseline.

## 2. Structure and ownership

```text
backend/                 Django settings, root URLs, WSGI/ASGI, Celery configuration
accounts/                User accounts, employee profiles, employee-ID allocation, roles
organization/            Company, branch, department and warehouse records/admin
core/                    Shared permissions, pricing/state rules, workflow guards, audit
logistics/               Public website, quotation/contact intake, services and carriers
dashboard/               Staff overview, real operational metrics and navigation context
customers/               Business customer records and staff CRUD
quotations/              Pricing, commercial validity and approval workflows
shipments/               Quote conversion, booking, transitions and delivery timestamps
operations/              Shared staff UI, reports, exports, stock ledger, proofs/settings
customer_services/       Customer authentication/registration, portal, tracking, outbox
payments/                Canonical customer invoice model and issuance/void services
finance/                 Payment ledger, outstanding balances and reconciliation
inventory/               Catalogue products, stock links, warehouses and reservations
orders/                  Sales-order lifecycle, lines, fulfillment and shipment linkage
procurement/             Suppliers, audits, requests, purchase orders and goods receipts
fleet/                   Vehicles, drivers, assignments, checkpoints and maintenance
integrations/            Odoo, Flutterwave, pawaPay, durable jobs and verification
security_controls/       MFA, session controls, request validation, security events/alerts
templates/, static/      Server-rendered interfaces and shared mobile components
deploy/, .github/        Deployment examples, dependency checks and security CI
```

Important ownership details:

- `finance.Invoice` is a **proxy** over `payments.Invoice`; it is not a second
  invoice table (`finance/models.py:7`). Invoice screens are routed through
  customer services, finance and the customer portal despite empty `payments/urls.py`.
- `inventory.Warehouse` proxies `organization.Warehouse`. `StockLevel` links a
  product to `operations.InventoryItem`; its quantity property reads the existing
  stock record (`inventory/models.py:6`, `:22`). These are compatibility layers,
  rather than independent warehouse/balance implementations.
- `organization/views.py` is boilerplate. Organization management currently relies
  on Django admin, while staff, inventory and commercial modules have custom screens.
- The legacy `dashboard.module_placeholder` view redirects registered routes to
  implemented modules. Its name is not evidence that reports/settings are missing.

## 3. Actual architecture and logic

```text
Public website / Staff workspace / Customer portal
                         |
          Middleware + authentication + permissions
                         |
                Django views and forms
                         |
         Workflow/services + reusable business rules
                         |
         Django ORM + transactions + record locks
              /                         \
     Business records             Audit/event/outbox records
                                         |
                              Celery tasks + Redis broker
                                         |
                         SendGrid / Twilio / Africa's Talking
                         Odoo / Flutterwave / pawaPay
```

The frontend uses Django templates, Bootstrap 5 in the workspace/portal, legacy
Bootstrap 4 in the public website and vanilla JavaScript progressive enhancement.
It is a responsive web application, not a native mobile app or public REST API.
SQLite supports local development; production settings require PostgreSQL with
verified TLS and a TLS Redis broker. A Vercel preview configuration exists alongside
traditional Nginx/Gunicorn deployment examples.

The architecture has useful safeguards: transaction boundaries, `select_for_update`,
record versions, idempotency keys, database constraints, service-controlled writes,
permission-filtered QuerySets and append-only application audit records. Signals
connect shipment/order state and enqueue notifications/integrations; durable jobs
and leases support retries. These are meaningful business implementations.

Core flows and limits:

- **Quotations:** pending → reviewed → approved, with rejection/reopening paths.
  Price uses base amount + weight × rate + surcharge − discount, then tax, with
  decimal rounding, finite-number checks and validity dates. Default policy is
  local UGX/international USD; above UGX 50,000,000 or USD 15,000 requires Admin
  approval. The preparer cannot approve their own quotation. Policy is configurable
  (`core/business_rules.py`, `quotations/workflows.py`, `operations/policy.py`).
- **Shipments:** an approved, valid quotation converts atomically into one shipment;
  retries return the existing booking. Pending → in transit → delivered/cancelled
  is guarded, timestamped and audited. Terminal records are locked. Linked orders
  and fleet availability are checked before dispatch (`shipments/workflows.py`).
- **Orders:** draft → submitted → approved → fulfilled → shipped → closed, with
  allowed cancellation paths. Every approval requires a different Admin approver.
  Order totals must match the quotation. Approval reserves stock; fulfillment issues
  stock and links the booking; closure requires delivered status (`orders/services.py`).
- **Procurement:** audited/active suppliers, approved requests, purchase budgets,
  separate Admin approvals, partial receipts, over-receipt prevention and idempotent
  receipt references are implemented (`procurement/services.py`).
- **Finance:** positive, same-currency payments cannot exceed document balances.
  Payment references/idempotency keys are protected; posted payments are retained.
  Statement matching checks exact amount, currency, direction and reference. A
  ledger reversal is explicitly not a provider refund (`finance/services.py`).
- **Fleet:** dispatch checks vehicle service limits, driver status/licence, cargo
  capacity and exclusive assignments. Tracking is staff-entered checkpoint history;
  it is not an automated GPS feed (`fleet/services.py`).

## 4. Feature inventory

| Area | Implemented | Missing or awaiting acceptance |
| --- | --- | --- |
| Public website | Company/service/contact/FAQ pages, validated quote/contact intake | Production content review and measured performance/accessibility acceptance |
| Staff access | Authentication, role/model permissions, employee lifecycle, safe deactivation | Dedicated staff-portal password recovery/change screens are not wired; Django admin retains its built-in password-change facilities. Organization-wide access needs branch policy if required |
| Dashboard/mobile UI | Real permission-filtered metrics, charts, desktop navigation, mobile drawers, responsive record cards/forms, toasts, skeletons, pagination, empty states and confirmation dialogs | Physical-device/screen-reader acceptance, production performance budgets and repeatable browser CI |
| Customers | Staff create/list/edit, details and portal access administration | Full customer account administration/branch scoping policies where required |
| Quotations | Aggregate pricing, UGX/USD policy, approval thresholds, validity, audit/version checks | Quotation line items, individual quotation PDFs, customer online acceptance/rejection and revisions |
| Shipments | Booking, tracking IDs, state transitions, details/history and delivery timestamps | Split shipments, automated carrier/GPS feeds, route optimization and advanced exception handling |
| Proof of delivery | Recipient/time, validated PDF/JPEG/PNG uploads, hash/audit references, protected downloads and exports | Signature-pad UI if desired; malware scanning, retention and independent storage/encryption acceptance |
| Inventory | Products, warehouses, balances, receipts/issues, low-stock indicators, reservations and stock movement audit | Transfers, bins, barcode picking, batch/serial/expiry tracking, cycle-count workflows and costing/valuation are advanced extensions |
| Orders | Admin approval, lines, stock reservation, fulfillment, dispatch and closure | Partial fulfillment, split deliveries, returns and post-fulfillment adjustment workflows |
| Procurement | Supplier CRUD/audits, requests, purchases, Admin approvals, receiving and supplier payment linkage | Supplier portal, RFQ comparison, purchase returns and richer supplier performance workflows |
| Fleet | Vehicle/driver CRUD, assignments, maintenance and manual coordinates/checkpoints | Live telematics/GPS, automatic location ingestion, route planning and richer cost reporting |
| Finance | Invoice issue/void/PDF, customer/supplier payments, balances, statement CSV import and reconciliation | Gateway refunds, credit notes, settlement/fee treatment and statutory/accounting sign-off; this is not a full general ledger |
| Customer services | Self-registration/email-code verification, optional invitations, owned quotes/shipments/invoices/proofs, notifications, preferences and password recovery | Real email/SMS acceptance; customer quotation acceptance and broader self-service order flows |
| Public tracking | Whitelisted status timeline, ETA and proof-recorded confirmation | Automated carrier events; full private audit/evidence must continue to stay behind authentication |
| Notifications | Durable outbox, Celery retry/lease logic, SendGrid, Twilio and Africa's Talking fallback | Verified live delivery, receipts/bounce webhooks, supervised workers/beat and operational alerts |
| Integrations | Odoo JSON-2 invoice/purchase export, Flutterwave collection/verification/webhook, pawaPay collection/verification polling, retries/recheck screens | Live sandbox/merchant/accounting acceptance, refunds and broader/bidirectional ERP synchronization |
| Security | Shared lockout, TOTP MFA/recovery codes, encrypted MFA secrets, session expiry/revocation, CSRF/CSP, bounded inputs, strict JSON, redacted logs and security alerts | External monitoring/alert forwarding, immutable audit protection, retention, malware scanning and infrastructure acceptance |
| Reports/admin | QuerySet search/pagination, date/status/staff filters, CSV/PDF exports and configurable business policy | Dedicated company/branch/department screens, scheduled reports and advanced BI |
| APIs/deployment | Provider callback/payment routes, Django/Vercel configuration, CI definitions and deployment examples | General REST API/mobile API, production rollout, Linux/PostgreSQL acceptance and release operationalization |

### Important storage and integration distinctions

Delivery-proof bytes are stored in `operations.DeliveryProof.evidence`, a database
`BinaryField` (`operations/models.py:103`). They already persist with PostgreSQL and
are served through permission-controlled views. General statements that every proof
upload still needs filesystem persistence are inaccurate. Company logos and staff
photos are `ImageField`s using `MEDIA_ROOT`; those need durable private hosting and
delivery policy. Keeping proofs in the DB also requires capacity/backup planning.

Odoo export deliberately leaves accounting documents in draft and checks remote
amount/currency; it does not implement a complete ERP or autonomous accounting
posting (`integrations/adapters.py`). pawaPay verification uses jobs/polling; the
only dedicated provider webhook in current URLs is Flutterwave.

In production mode, self-registration is intentionally unavailable unless email
delivery is configured (`customer_services/registration.py:22`). With the recorded
demo settings disabling provider traffic, creating a real customer account cannot
complete just because the registration page exists. Redis provisioning alone does
not run Celery workers or beat.

## 5. Release defects and architectural debt

| Priority | Finding | Evidence / consequence |
| --- | --- | --- |
| Resolved: release | Conflicting Linux Gunicorn dependencies | Runtime and production requirements are separated; the production Gunicorn pin no longer conflicts with the runtime file. Linux CI installs the production dependency set. |
| Resolved: release | Git dashboard path casing | The tracked package is normalized to lowercase `dashboard/`, matching Python imports on case-sensitive systems. |
| Resolved: release | Invalid Vercel builder override | Removed an untracked legacy `vercel.json` whose builder source did not exist; Django framework discovery uses root `manage.py`. |
| Resolved: release | Linux application checks | CI now runs security scan, Django system/migration checks and the app test suite on Linux as well as Windows. |
| Resolved: maintainability | Runtime dependency contamination | Runtime, Linux production and security/development requirements are split; dev/security tools and duplicate PostgreSQL drivers are not installed by the app runtime file. |
| Resolved: documentation | Stale architecture and roadmap | Architecture reflects current source; README/ROADMAP no longer report MFA as unimplemented. |
| P1: access | Branch-level isolation is absent | Staff permissions currently cover the organization. Agree branch/department record scope, then apply it consistently to QuerySets, form choices, exports and service authorization if NASIL requires separation. |
| P1: operations | Production worker/storage/backup/monitoring acceptance is missing | Configuration and examples exist; they are not proof of supervised delivery, durable media, encrypted off-site backups, restore drills or tested alerting. |
| P1: integration | Real provider/accounting acceptance is outstanding | Adapters and mocked tests do not establish merchant enablement, settlement handling, delivery receipts or correct Odoo mappings/localization. |
| P2: architecture | Cross-app orchestration is tightly coupled | Orders, shipments, inventory and fleet call one another and use signals/local imports. Keep the monolith; document ownership/lock order and centralize orchestration/contracts as flows expand. |
| P2: automation | PostgreSQL/browser CI coverage is incomplete | Linux application tests are now configured. PostgreSQL concurrency and repeatable browser QA remain outside CI; the four PostgreSQL-only checks were skipped locally. |

The one-to-one links between quote, order, shipment and invoice encode a simplified
business lifecycle. Split dispatch, partial fulfillment and returns require an
explicit model/workflow design; they should not be added by bypassing terminal-state
or stock controls. Similarly, reconciliation currently matches one statement line
to one payment with exact references/amounts; grouped settlements/fees need design.

## 6. Verification and recommended implementation order

Fresh checks on 12 November: Django system checks passed, no missing model migrations
were detected, and the 417-file source regression scan passed. No provider traffic
was enabled and no production records were changed for this review.

Last full test evidence (11 November): 214 tests run, 210 passed and four PostgreSQL
checks skipped. Subsequent focused suites passed. Mobile evidence covers 405
page/viewport combinations across nine widths, eight interaction checks, and
additional internal portal-table clipping checks. These are local regression results,
not proof of production load, real provider delivery or WCAG certification.

The 27 October Vercel preview is recorded as built successfully. The mobile changes
were not redeployed in the last task, and the original seven-day client share link
has passed its original validity window. Remote deployment health and any subsequent
changes were not checked in this review.

Recommended phases after the release fixes are committed:

1. **Release baseline:** resolve dependency and Git casing blockers; clean dependency
   separation; reconcile documentation; review/commit/push the complete working tree.
2. **Operational pilot:** agree branch/access policy, verify staging on PostgreSQL,
   supervise Celery/beat, finish media/backup/restore/monitoring setup, and run staff
   acceptance plus realistic concurrency/load checks.
3. **Live customer/commercial services:** accept SendGrid/SMS delivery and recovery,
   verify Flutterwave/pawaPay sandbox flows, settle Odoo mappings/accountant sign-off,
   then enable services deliberately and renew the client demonstration deployment.
4. **Business expansion:** quotation line items/PDF/acceptance; returns, partial/split
   fulfillment and settlement/refund workflows; advanced warehouse/fleet functions;
   REST API, offline/mobile features and BI according to confirmed business priorities.

Kubernetes, microservices and a frontend framework rewrite are not prerequisites
for this application's next useful release. Complete the operational baseline and
high-value business gaps before introducing that infrastructure.
