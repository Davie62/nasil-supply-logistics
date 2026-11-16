# NASIL Supply & Logistics

A Django application with a public company website and permission-controlled staff workflows.

## Implemented

- Public company pages, validated quotation requests and contact enquiries.
- Staff login/logout and repeated-login-failure lockout on the custom login view.
- Customer, quotation, shipment, carrier and service list/create/edit workflows.
- Contact-message viewing and an explicit, CSRF-protected mark-as-read action.
- Dashboard counts and shipment status chart filtered by model permissions.
- Organization and employee administration through Django admin.
- Default staff roles with model permissions; database-backed employee ID allocation.
- Quotation pricing and validity; UGX for local and USD for international work.
- Separate quotation approval and atomic conversion into a single shipment.
- Admin approval above UGX 50,000,000 or USD 15,000; preparers cannot self-approve.
- Validated shipment transitions, timestamps and append-only business audit history.
- Quotation, shipment, inventory and staff detail screens; server-side list search and pagination.
- Warehouse inventory with audited receipts/issues, balances and reorder levels.
- Staff lifecycle screens with safe deactivation and protected account roles.
- Filtered operational reports and audited CSV/PDF exports; private uploaded delivery proofs.
- Administrator settings for approval limits, supported currencies and dashboard alerts.
- Customer self-registration with email-code verification, optional staff invitations, and owned quotations, shipments, invoices and delivery evidence.
- Redacted public tracking, customer notification preferences and queued email/SMS delivery.
- SendGrid, Twilio and Africa's Talking adapters with Celery retries and SMS fallback.
- Finance invoice issuance, snapshots, void history and audited PDF downloads.
- Commercial apps for payments/reconciliation, products/warehouses, orders, procurement and fleet operations.
- Odoo JSON-2 accounting exports and verified Flutterwave/pawaPay payment adapters with a durable integration queue.
- Separate Admin approval for every order, procurement request and purchase order; stock reservations and audited fulfillment/receiving.

See BUSINESS_RULES.md for policy, Django model examples, reusable validation and workflow usage.
See INTERNAL_OPERATIONS.md for internal screens, permissions, reports, upload handling and export examples.
See CUSTOMER_SERVICES.md for portal access, notification configuration, workers and Django examples.
See COMMERCIAL_OPERATIONS.md for commercial workflows, integration configuration, examples and live setup requirements.
See SECURITY_IMPLEMENTATION.md for MFA enrollment, session controls, encrypted secrets, validation, security logging and production requirements.

## Planned

Provider sandbox acceptance and live payment configuration, refunds, complete audit coverage, quotation line items/customer acceptance,
individual quotation PDFs, notification delivery receipts and a REST API remain pending.
Provider adapters need credentials and live staging verification. See ROADMAP.md for the
phased implementation plan and REMEDIATION.md for the current verified baseline.

## Local setup (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-development.txt
$env:DJANGO_DEBUG = 'true'
python manage.py migrate
python manage.py seed_roles
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/. The explicit local DEBUG setting is required for every
new terminal session unless you copy `.env.example` to `.env`: Django loads `.env`
automatically and real environment variables always take precedence. Local
development uses SQLite and a stable development-only signing key; supply a private
DJANGO_SECRET_KEY for any shared environment.

`requirements.txt` contains application runtime dependencies. Linux deployments
that use Gunicorn should install `requirements-production.txt`; the Vercel Django
build uses the runtime file. Security/development tooling is in
`requirements-security.txt` and `requirements-development.txt`.

## Docker development stack

`docker compose up --build` starts PostgreSQL, Redis, a migration job, Django on
http://localhost:8000, a Celery worker and beat. The stack runs with
`DJANGO_DEBUG=true` over plain HTTP; it is not a production configuration. On
first use run `docker compose run --rm web python manage.py seed_roles` and create
a superuser. Health probes are `GET /healthz` (liveness) and `GET /readyz`
(database and, when enabled, broker readiness).

`seed_system` additionally creates sample company/branch/department/warehouse
records. Use it only for a new development installation. On existing installations,
use `seed_roles`, which does not change organization records or user memberships.

Use a superuser to mark employees as **staff** and assign the appropriate group.
Staff status alone does not grant access to business modules. All current custom
business permissions apply across this single organization's records; branch-level
staff isolation is not implemented. Customer portal records are scoped to their owner.
Default groups cannot administer users
or group memberships. Only explicitly granted Django admin permissions or superuser
access permit those operations.

Staff saved before an active organization department exists are not provisioned
with an employee profile until they are saved again after configuration. Employee
profiles always use their department's branch.

## Verification

```powershell
$env:DJANGO_DEBUG = 'true'
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
python -m ruff check .
```

`python -m pytest` is available as an optional runner using the configuration in
`pyproject.toml`; `manage.py test` remains the canonical suite.

The PostgreSQL concurrency tests skip on SQLite. Run the same suite against a
separate PostgreSQL test database before production; the database user needs
permission to create a test database. Production configuration and operations are
documented in DEPLOYMENT.md.
