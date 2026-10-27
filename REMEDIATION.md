# Priority remediation and security inventory

Reviewed and updated on 26 October 2026. This is the verified local baseline;
ROADMAP.md defines the remaining delivery phases; SECURITY2.md describes intended policy.

## 1. Scope and method

Applied the repository's `.github/skills/django-security-audit/SKILL.md` with explicit
remediation authorization. Reviewed backend settings/URLs, every installed local app,
models/migrations, views/forms/services/signals, admin, seed commands, shared templates,
static assets, tests, dependency files, ignore rules and security/architecture documents.
Preserved existing working-tree changes and added fixes on top. No deployment or
external messages were performed.

Ran Django regression/system/migration checks, deployment security checks using
non-live PostgreSQL configuration, local migration/backfill checks and browser checks
against a separate SQLite QA database. Production dependencies were installed in the
existing virtual environment; Gunicorn is Linux-only and was not executed on Windows.

## 2. Global implemented controls

- Django authentication, ORM, CSRF middleware, template escaping and clickjacking
  middleware remain enabled in backend/settings.py.
- Production defaults disable DEBUG and require a stable private signing key, explicit
  allowed hosts and PostgreSQL credentials. HTTPS redirect, HSTS, secure session/CSRF
  cookies, HTTP-only cookies and same-site flags are configured.
- Forwarded-protocol trust is opt-in; it requires a correctly configured private proxy.
- Internal business views use core/permissions.py to require an active staff account
  and the relevant view/add/change model permissions. Guests are redirected to login;
  authenticated users without access receive 403.
- Role defaults are populated through accounts/roles.py and seed_roles/seed_system.
  Defaults do not include user or group administration. Existing custom grants are
  preserved and need administrative review.
- Production configuration includes PostgreSQL TLS verification, STATIC_ROOT, console
  logging, example Gunicorn/nginx configuration and environment documentation.

## 3. App-by-app inventory

| App | Verified mechanisms and current limits |
| --- | --- |
| accounts | Custom users; custom-login lockout; POST logout; staff-only, idempotent employee provisioning; atomic database counter for employee IDs; nullable unique optional phone; admin user creation requires email. MFA, recovery flows and global authentication-backend lockout remain incomplete. |
| organization | Admin model permissions, relational organization records, shared soft deletion and UUID metadata. Default department selection now uses its actual active branch. No custom organization workflow or branch-level business isolation. |
| core | Staff/model permissions for enquiry lists/details; GET has no read-state mutation; explicit POST mark-as-read needs change permission and CSRF. No immutable business audit trail. |
| dashboard | Staff-only entry; model-permission-filtered metrics; active employee profiles counted correctly; real status chart including cancellation and neutral empty state. Employee navigation opens employee admin; reports/settings honestly show planned status; no false payment actions. |
| logistics | Validated public contact/quote submissions, field errors and retained values; normalized customer email; atomic customer-plus-quote saving. Staff/model permissions on carrier/service workflows; missing records return 404. Public abuse throttling is absent. |
| customers | View/add/change permissions on existing staff workflows; hidden edit/create links when unauthorized; admin search/filter support. No customer login identity or record ownership boundary. |
| quotations | Public form cannot choose customer IDs or approval status; positive weight validation now also rejects zero; management permissions. No distinct approval authority, pricing engine, transition policy or PDF generation. |
| shipments | Existing staff workflows now enforce model permissions. Tracking references and manual status/location fields exist; lifecycle enforcement, event history and public tracking remain incomplete. |
| payments | No implemented payment security controls found: models/views/URLs remain scaffolding. Dashboard does not offer payment recording. |

## 4. Documented but unverified controls

README claims were reconciled with working features and planned features.
SECURITY2.md merge-conflict markers were removed and the document is labeled as
policy rather than proof of implementation. MFA, general API throttling, a REST API,
AES-256 application encryption, Argon2 selection, customer self-service, immutable
business audit logs, notification delivery, deployed monitoring, automatic backups
and a verified production release are not established by this work.

## 5. Security gaps and recommendations

### Addressed priority defects

1. Employee provisioning: fixed missing return and unsafe max-plus-one allocation;
   added a transactional per-year database counter and legacy-ID backfill. Multiple
   missing employee phones are stored as NULL. Normal customers are not auto-created
   as employees. The admin creation form collects required unique email addresses.
2. Public input handling: bound Django forms validate before writes, reject malformed
   and non-positive weights, show field errors, retain values, and normalize email.
   A quotation write failure rolls back a newly created customer.
3. Authorization: every current custom business CRUD/read endpoint checks staff and
   model permissions. View-only roles cannot submit writes. Model authorization is
   organization-wide, not a tenant/branch ownership implementation.
4. Dashboard integrity: repaired routes/actions, replaced false financial/activity
   claims, hid inaccessible controls, and computed all chart proportions from records.
   Repaired missing public icon stylesheet references and malformed checkmark text.
5. Production baseline: guarded environment configuration, PostgreSQL settings/driver,
   collected-static path, logging and server examples. Deployment operations are
   documented in DEPLOYMENT.md; no live hosting configuration was changed.

### Remaining work for the phased roadmap

- High: enforce quotation approvals and shipment transitions in shared services and
  database constraints, including admin behavior; design customer/branch ownership
  before exposing multi-tenant or self-service access.
- High before launch: verify the deployment on real PostgreSQL, execute concurrency
  tests, configure HTTPS/proxy supervision, migrate data, configure encrypted scheduled
  backups, test recovery and configure external alerts.
- Medium: apply lockout/rate controls consistently to admin and other authentication
  entry points; add public-form abuse throttling and improve lockout expiry behavior.
- Medium: implement immutable business auditing, password recovery, email verification,
  MFA as required, and authenticated delivery/validation of uploaded employee photos.
- Medium: enforce numeric invariants at model/database level as well as custom forms,
  validate existing data before adding constraints, and add relationship-specific
  permissions/ownership filters to form choices where the business requires them.
- Planned features: pricing, PDF documents, operational reports/search/pagination,
  customer portal/tracking, payments, notifications, procurement/inventory and API.
- Maintenance: reconcile the original architecture/database documents and lock
  production dependencies for a reproducible release once the hosting target is chosen.

## 6. Security test plan and executed results

Django discovered 39 tests: **38 passed; 1 PostgreSQL-only concurrency test skipped**.
Executed coverage includes guest/nonstaff/unprivileged access across business routes,
view-only write rejection, successful CRUD, CSRF rejection, POST-only logout, custom
login lockout, invalid public inputs, preservation of submitted values, transaction
rollback, repeated employee creation, staff promotion, legacy counter initialization,
optional phones, role defaults, required admin email, dashboard permissions/chart data,
and guarded production settings.

`manage.py check` passed; `makemigrations --check --dry-run` found no changes.
`manage.py check --deploy --fail-level WARNING` passed using temporary non-live
PostgreSQL configuration. This checks configuration, not database connectivity or TLS.
The local database was backed up with SQLite's backup API and integrity-checked before
accounts.0003_employee_identifiers was applied. seed_roles was run without changing
user memberships.

Playwright exercised a server-side negative-weight error with retained values, staff
login and the dashboard at desktop/mobile sizes. Screenshots are under the ignored
output/playwright directory. No real customer data was used for browser testing.

Before production: run the suite on an isolated PostgreSQL database (including
accounts/test_concurrency.py), test actual TLS/proxy behavior, enforce administrator
login protection, exercise ownership boundaries once defined, test malicious uploads,
verify backup restoration and perform load testing. These are not replaced by the
local suite.

## 7. Assumptions and residual risk

The current permission boundary is a single internal organization. Staff users still
need explicit group/model grants. No existing users were promoted or assigned groups.
Use a superuser to review memberships and legacy custom grants. Setting a group does
not implicitly enable staff status.

Development now explicitly requires DJANGO_DEBUG=true in each terminal. The local
fallback key is stable for convenience and is unsuitable for shared environments;
production rejects it. A .env example is documentation, not automatic secret loading.

No real PostgreSQL server, Linux process supervisor, nginx deployment, live certificate,
external monitoring, off-site backup store, restore drill, penetration test or load test
was available for this verification. Protected media is blocked in the nginx example
until an authenticated delivery path is implemented. The implementation is a stronger
local baseline, not a production-readiness certification.
