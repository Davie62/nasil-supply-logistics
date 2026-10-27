# NASIL implementation roadmap

Updated 27 October 2026 against the working code. This supersedes the original
phase-completion claims. See REMEDIATION.md for evidence and DEPLOYMENT.md for
configuration and launch operations. No calendar estimates are assigned until
business rules and the hosting target are agreed.

## Existing baseline

The public company website, quote/contact intake, basic customer/quotation/shipment/
carrier/service management, staff login, organization models/admin and dashboard
are implemented. Customer accounts, public tracking, invoice documents and queued
provider notifications are now implemented; see CUSTOMER_SERVICES.md. Commercial
orders, procurement, fleet, catalogue inventory, payment verification and Odoo
adapters are implemented locally; see COMMERCIAL_OPERATIONS.md. Provider sandbox
acceptance, production enablement, a public REST API and MFA remain pending.

## Phase 0 - Priority defect remediation

Status: implemented and verified locally.

- Fix employee ID allocation, optional phone uniqueness, repeated provisioning,
  department/branch consistency and required email on admin user creation.
- Validate anonymous quote/contact inputs before writes; preserve values/errors;
  make customer-plus-quote creation atomic.
- Require staff and appropriate model permissions on existing internal workflows;
  populate conservative role defaults and hide inaccessible actions.
- Remove GET read-state mutation, misleading dashboard links and hardcoded metrics;
  use real shipment chart proportions and clearly mark planned modules.
- Guard production secrets, DEBUG, hosts and database settings; add production
  dependencies, static configuration, logging and example server configuration.
- Back up and migrate the local database; preserve existing business records and
  user memberships. Add regression coverage and perform browser checks.

Evidence: 38 tests passed, 1 PostgreSQL concurrency test skipped; system, migration,
deployment-configuration and static collection checks passed. A live production
installation and PostgreSQL concurrency verification remain launch requirements.

## Phase 1 - Business rules, access boundaries and traceability

Dependency: Phase 0. Status: core quotation/shipment rules implemented locally;
remaining access, authentication and production verification work is listed below.

Implemented: aggregate pricing, local UGX/international USD policy, taxes/validity,
maker/approver separation, Admin approval above UGX 50,000,000 or USD 15,000,
transactional conversion, legal shipment transitions/timestamps, audit diffs,
legacy snapshots, numeric checks and guarded UI/admin/ORM writes. See BUSINESS_RULES.md.

Remaining:

- Define and document the role/action matrix, branch ownership policy and separate
  quotation approval authority across all modules. Review pre-existing grants.
- Add quotation line items and customer acceptance when their requirements are agreed.
- Require future integrations to reuse the implemented workflow services.
- Extend numeric/relationship checks to other business modules as needed.
- Extend audit coverage beyond quotations/shipments; define retention and stronger
  tamper-resistance requirements where required.
- Extend authentication controls across admin/login entry points, add password
  recovery and public-form abuse throttling; implement authenticated upload delivery.
- Run the suite and employee ID concurrency tests against an isolated PostgreSQL DB.

Completion criteria: invalid transitions, unauthorized approvals and cross-boundary
access are rejected in every entry point; operations are atomic; important changes
are traceable; regression tests exercise both allowed and denied behavior.

## Phase 2 - Complete internal operations

Dependency: Phase 1.

Status: requested internal operations implemented locally. See INTERNAL_OPERATIONS.md.
Detail screens, reusable tables/search/pagination, filtered reports with CSV/PDF,
private uploaded delivery evidence, staff lifecycle and business-policy settings
are available. Basic warehouse inventory now has its own auditable stock ledger.

Remaining extensions:

- Generate individual quotation PDFs; invoice PDFs, reports and delivery proofs
  are implemented. Agree statutory invoice numbering and finance requirements.
- Extend document handling beyond delivery evidence where required.
- Complete dedicated company/branch/department administration screens; these still
  use Django admin. Reconcile older architecture/database descriptions.
- Add further archival workflows where business retention rules require them.

Completion criteria: authorized staff can complete quote-to-delivery work without
manual database edits; lists remain usable with realistic volumes; reports and
exports agree with the underlying records; employee lifecycle actions are tested.

## Phase 3 - Customer communication and self-service

Dependency: Phases 1-2. Launch gate applies before external access.

Status: requested customer services implemented locally, with self-registration,
email-code verification, optional invitations, owned quotations/shipments/invoices/proofs, preferences, in-app updates,
password recovery and redacted public tracking. SendGrid email and Twilio SMS with
Africa's Talking fallback use a durable outbox and Celery retry/lease handling.
See CUSTOMER_SERVICES.md for examples and setup. Full suite: 142 passed, four
PostgreSQL-only checks skipped. No real messages were sent.

Remaining: configure provider credentials, Redis/workers/beat and canonical HTTPS
origin; validate real provider delivery and PostgreSQL concurrency in staging.
Add delivery receipt webhooks and any additional intake/customer-acceptance events
when required. Set retention and monitoring policies before launch.

Completion criteria: customers can access only their own permitted records; tracking
reveals only approved information; notification retries do not duplicate business
operations and failures are visible to staff.

## Phase 4 - Payments and financial reconciliation

Status: local implementation now includes invoice-linked and supplier payments,
bank statement import/matching/closure, verified Flutterwave/pawaPay collection,
idempotency, review/recheck screens and finance permissions. All automated traffic
is disabled by default. See COMMERCIAL_OPERATIONS.md. Remaining work in this phase
is provider sandbox acceptance, merchant configuration, refunds and production rollout.

Dependency: approved pricing/invoicing rules from Phases 1-2. Can follow the first
internal production pilot; not required merely to launch staff operations.

- Configure the selected Flutterwave and pawaPay accounts and enabled currencies/methods.
- Validate credentials, provider verification, duplicate/reordered notifications and amount mismatches in sandbox.
- Add provider-appropriate refund workflows and any required settlement-fee accounting.

Completion criteria: provider sandbox tests cover success, failure, cancellation,
duplicate/reordered webhooks and amount mismatches; payment state is reconciled
against the provider before showing a transaction as settled.

## Phase 5 - APIs and external integrations

Status: Odoo 19/20 JSON-2 draft invoice/purchase exports, cancellation guards,
environment-based mappings, readback validation and durable retries are implemented.
Live Odoo acceptance and accounting/localization sign-off remain pending. A public
REST API, carrier feeds and automated GPS integration are separate future work.

Dependency: stable services and ownership boundaries from Phase 1. Optional for the
first release; implement when a mobile client or integration needs it.

- Add REST API schemas, authentication, authorization, validation and throttling.
- Reuse the business services rather than duplicate rules in API views.
- Add versioning, documentation and contract tests.
- Integrate carrier status updates, supplier systems or GPS only where required;
  define synchronization ownership and failure/retry behavior.

Completion criteria: API and UI enforce the same rules; credentials are scoped;
contracts are documented and integration failures cannot silently corrupt records.

## Phase 6 - Production launch and operational handover

Begin staging preparation during Phase 1. This is a mandatory gate before any real
internal or customer production release, including an early pilot after Phase 2.
Do not wait for optional payments/API modules to prepare it.

- Choose the host, provision PostgreSQL, migrate/validate existing data and separate
  development/staging/production secrets and services.
- Deploy a supervised WSGI/ASGI service and HTTPS reverse proxy; configure static
  serving and authenticated, persistent uploads.
- Install immutable/reproducible release dependencies and CI checks.
- Configure encrypted off-site database/media backups, retention and restore drills.
- Configure application/database readiness probes, logs, error monitoring and alerts.
- Validate actual proxy/cookie/TLS behavior, role memberships and PostgreSQL concurrency.
- Run realistic load tests, security testing and staff acceptance testing.
- Document release, rollback, incident response and recovery procedures.

Completion criteria: staging acceptance passes, a backup has been restored into an
isolated environment, monitoring alerts have been tested, release/rollback procedures
work, and an authorized business owner accepts the pilot scope.

## Later expansion

Procurement requests/purchases, supplier audits, catalogue stock reservations,
order fulfillment, fleet assignments, manual route checkpoints and maintenance
are implemented locally in separate apps. Every order and purchase requires a
different Admin approver. Advanced warehouse picking, mobile apps, automated GPS,
route optimization and advanced business intelligence remain future expansion.

## Suggested delivery order

1. Complete Phase 1 business/security rules.
2. Complete Phase 2 for a useful internal MVP, while preparing Phase 6 staging.
3. Pass Phase 6's launch gate for an internal pilot.
4. Add Phase 3 customer self-service, repeating the launch gate for external access.
5. Schedule Phase 4 payments and Phase 5 APIs according to business value.
