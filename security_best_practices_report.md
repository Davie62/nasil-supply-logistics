# NASIL security audit and remediation status

## 1. Scope and method

Reviewed 27 October 2026: `backend/settings.py`, root/app URLs, every installed local
app, authentication/admin, models, forms/services/signals, templates, uploads,
outbound adapters, migrations, management/seed scripts, ignore rules and dependency
files. Methods: source review, targeted SQL/unsafe HTML/execution/CSRF searches,
AST/credential-pattern regression scan, isolated Django security/regression tests,
dependency advisory queries and isolated browser QA. No production access or live
financial transactions were used. This is an OWASP-aligned review, not certification.

## 2. Global implemented controls

- Shared atomic password lockout covers staff, customer and Django admin authentication
  in [backends.py](security_controls/backends.py#L10). Django password validators now
  require 12 characters; passwords remain one-way hashed.
- Authenticator MFA, replay prevention, hashed one-use recovery codes and encrypted
  secrets are in [mfa.py](security_controls/mfa.py#L18) and
  [crypto.py](security_controls/crypto.py#L1). Staff MFA is mandatory in production.
- Absolute/idle session expiry, MFA gating, session revocation and abuse limits are in
  [middleware.py](security_controls/middleware.py#L1). Browser actions retain CSRF.
- Bounded query/form inputs, duplicate detection, strict JSON and CSP are implemented
  in that middleware and [validators.py](security_controls/validators.py#L1).
  ORM parameterization and automatic HTML escaping remain the injection protections.
- Metadata-only centralized JSON logging, request IDs, fingerprinted IPs and read-only
  events/alerts are in [events.py](security_controls/events.py#L1),
  [logging.py](security_controls/logging.py#L1) and [admin.py](security_controls/admin.py#L1).
- Production config rejects missing encryption keys, disabled mandatory staff MFA,
  unverified database TLS and non-TLS Redis. Proxy trust is explicit. HSTS scope is
  operator opt-in. Development keys are random files under ignored `.local/`.

## 3. App-by-app inventory

All statuses describe executable controls; every app inherits global middleware.
"Partial" identifies remaining boundaries/operational work rather than a proven exploit.

| Local app | Status and mechanisms | Evidence / remaining boundary |
| --- | --- | --- |
| accounts | Implemented authentication, password hashing, staff lifecycle and role checks | `accounts/views.py`, `roles.py`, `services.py`; shared backend closes admin lockout gap |
| organization | Partial: Django admin model permissions, relational constraints, private media default | `organization/admin.py`, `models.py`; no branch ownership isolation or complete media delivery |
| core | Implemented staff permission decorator, form validation, append-only audit APIs | `core/permissions.py`, `forms.py`, `models.py`; independent audit protection remains operational |
| dashboard | Implemented staff/permitted-module views and counts; no own data models found | `dashboard/views.py`, `presentation.py`, `context_processors.py`; Linux directory-case verification remains a deployment check |
| logistics | Implemented typed public intake, atomic writes, staff permissions and intake throttling | `logistics/views.py`, `forms.py`; legacy public-theme plugin maintenance remains |
| quotations | Implemented pricing validation, approval authority, version checks, guarded writes | `quotations/forms.py`, `workflows.py`, `models.py`; staff scope is organization-wide |
| shipments | Implemented state validation, protected conversion, traceable transitions | `shipments/forms.py`, `workflows.py`; GPS/provider feeds not active |
| payments | Implemented guarded invoice snapshots and issuance/void services | `payments/models.py`, `services.py`; no standalone payment views/URLs found; exposed through finance/customer services |
| customers | Implemented staff model permissions and validated CRUD | `customers/views.py`, `forms.py`; customer contacts are not branch-isolated |
| operations | Implemented permissions, stock invariants, private proof downloads and audited exports | `operations/services.py`, `views.py`, `exports.py`; malware scanner/retention not deployed |
| customer_services | Implemented ownership filters, verified registration, throttling, redacted tracking and notification queue | `security.py`, `registration.py`, `tracking.py`, `tasks.py`; real delivery/edge/retention acceptance remains |
| finance | Implemented document/currency/balance checks, idempotency and reconciliation guards | `finance/services.py`, `models.py`, `urls.py`; ledger receipt is not a provider refund |
| inventory | Implemented managed stock ledger, reservation checks and catalogue services | `inventory/services.py`, `models.py`; access is organization-wide |
| orders | Implemented service-only transitions, separate Admin approval and reservations | `orders/services.py`, `models.py`; existing module permissions remain authoritative |
| procurement | Implemented supplier audit/budget checks, Admin approval and idempotent receipts | `procurement/services.py`, `models.py`; organization-wide scope |
| fleet | Implemented active staff/licence/capacity checks, exclusive assignment and validated coordinates | `fleet/services.py`, `models.py`; route inputs remain staff-managed |
| integrations | Implemented bounded HTTPS transport, host/IP allowlists, redacted errors and authoritative gateway verification | `integrations/http.py`, `adapters.py`, `views.py`; provider callbacks/sandbox credentials require acceptance |
| security_controls | Implemented MFA, sessions, validation, encrypted secret utilities, events and alerts | `security_controls/`; DB/host operators remain privileged, external log forwarding not deployed |

## 4. Documented but operationally unverified controls

Production certificate/proxy behavior, PostgreSQL row locking, disk/media/backup
encryption, secret-manager configuration, Redis/database network isolation, backup
restoration and external alert delivery cannot be established from local code.
The repository provides requirements/configuration and operator procedures rather
than evidence these services are provisioned. GitHub CI is configured locally but
has not executed remotely for these changes.

## 5. Security gaps and recommendations

1. **High, deployment gate:** verify encrypted storage, private service networks,
   real TLS/proxy behavior and secret recovery. Run PostgreSQL and Linux acceptance.
   Evidence: `DEPLOYMENT.md`, `backend/settings.py`, `deploy/nginx.conf.example`.
2. **High if branch separation is required:** agree scope and implement object/queryset,
   form-choice and export isolation. Existing staff/model access is deliberately
   organization-wide (`operations/module_ui.py:72`), not branch security.
3. **Medium:** connect malware scanning/quarantine and retention to delivery/company/
   employee uploads. Current size/content checks are not malware detection
   (`operations/services.py:199`). Keep authenticated attachment delivery.
4. **Medium:** forward structured alerts, define retention and incident response, and
   independently protect audit records. Application guards do not prevent privileged
   database modification (`core/models.py`, `operations/models.py`, security models).
5. **Medium/maintenance:** continue public-theme dependency review and migration to
   maintained components. Loaded jQuery/UI/Migrate and Bootstrap JS were refreshed;
   the legacy public Bootstrap 4 theme and older plugins still need lifecycle work.
   Unreferenced historical asset copies are not claimed to be audited dependencies.
6. **Maintenance:** the full transitive Linux production dependency lock, repository
   history/host secret scans and independent penetration/load tests remain release work.

## 6. Security test plan and evidence

Tests cover shared admin lockout, MFA enrollment/enforcement/replay/recovery reuse,
factor lockout, CSRF, role and ownership denials, idle/absolute expiration, all-device
revocation, malicious text escaping/parameterized searches, duplicate/bounded inputs,
JSON structure/numeric checks, encryption rotation, redacted logs, proxy trust and
deduplicated alerts. Existing quotation/order/procurement/payment invariants remain
in the full suite. See `security_controls/tests.py` and existing app security tests.

The initial dependency scan flagged four installed packages (including the audit
tool's filelock), with duplicate advisory records. Patched pins are Django 6.1.2,
Pillow 13.0.0, sqlparse 0.6.0 and audit-tool filelock 4.2.1. The subsequent installed
Windows environment OSV scan reported no known vulnerabilities; this does not certify
uninstalled Linux packages, frontend plugins or future advisory changes. Pipeline
checks and `requirements-security.txt` keep the scan reproducible.

Final local evidence: the full upgraded-stack suite ran 205 tests (201 passed,
four PostgreSQL-only skips). After restoring environment-based mode selection,
the security/accounts/configuration suite ran 40 tests (39 passed, one PostgreSQL
skip). Migration consistency and the 358-file source scan passed. Both security
migrations were applied locally after a verified SQLite backup; original data in
54 tables, integrity and foreign keys were preserved. Isolated browser checks
covered enrollment, recovery-code sign-in, all-device logout and a 390px-wide MFA
challenge without horizontal overflow. The local login endpoint returned HTTP 200
with CSP and private/no-store headers.

A production-settings dry check reported only the expected HSTS subdomain/preload
warnings: those policies remain opt-in until all relevant hosts are verified for
HTTPS. This is not evidence of a deployed certificate or production connectivity.

## 7. Assumptions and residual risk

Local development may use HTTP, SQLite and optional staff enrollment; the running
server can enforce MFA through its environment. Enrolled users always require MFA.
Production boot rejects weakened staff MFA/database/broker TLS configuration. Passwords
and real customer accounts were not reset for testing. Browser tests use an isolated
database and synthetic identities. Local checks do not replace production verification.
See [SECURITY_IMPLEMENTATION.md](SECURITY_IMPLEMENTATION.md) for configuration,
middleware/validator examples, enrollment, key rotation and operator recovery.

---

# Historical baseline — findings below predate remediation

The following original review is retained for traceability. Its descriptions of
missing authentication, middleware, CSP and session controls are superseded above.

Reviewed 27 October 2026. Scope: focused review of Django authentication/settings,
staff access patterns, customer throttling/tracking, uploads, integration entry points
and deployment examples. This is a code/configuration review; no live infrastructure,
penetration test, dependency vulnerability scan or exploit verification was performed.

NASIL already has Django password hashing/validators, CSRF and clickjacking protection,
production secure-cookie settings, model permissions, customer ownership checks,
approval separation, guarded workflows, application audit records, private delivery
proof downloads, redacted public tracking and verified/idempotent gateway receipt
posting. External provider traffic is disabled by default. No critical vulnerability
was established by this focused review. Priorities below include implementation gaps,
conditional access requirements and deployment controls awaiting verification.

## High priority — before external launch

### S01 — Unify and strengthen staff/admin authentication

Evidence: [accounts/views.py:12](accounts/views.py#L12) checks `locked_until` in the
custom login view and increments `failed_login_attempts` through read/modify/save.
[backend/urls.py:29](backend/urls.py#L29) exposes the standard `admin.site.urls`;
[backend/settings.py:77](backend/settings.py#L77) has no visible MFA middleware or
custom authentication backend enforcing the custom lockout on every login path.

Impact: the custom staff lockout is not consistently enforced through Django admin;
password compromise can expose privileged financial and staff functions.

Implement MFA for privileged users, a shared authentication/lockout policy covering
staff and Django admin, atomic attempt accounting and account/IP throttling. Add
audited staff recovery and MFA recovery codes, and restrict admin through a trusted
access gateway/VPN where practical. Verify any upstream controls before concluding
they are absent in a deployed environment.

### S02 — Define and enforce staff record boundaries where required

Evidence: [operations/module_ui.py:72](operations/module_ui.py#L72) begins resource
queries with `model.objects.all()` unless a resource supplies a custom queryset.
[DEPLOYMENT.md:70](DEPLOYMENT.md#L70) documents organization-wide grants and the
remaining branch ownership policy.

Impact: a user with model access can see organization-wide records under the current
design. This becomes a security gap if NASIL requires branch or departmental isolation.

Agree the role/action/branch matrix and review existing custom grants. If branch
isolation is required, scope list/detail/export/action queries and form choices, then
test denied cross-branch access. Preserve Admin maker/approver separation. Do not
describe this as a confirmed tenant escape: the current design is one organization.

### S03 — Complete production infrastructure security and acceptance

Evidence: [DEPLOYMENT.md:4](DEPLOYMENT.md#L4) explicitly leaves deployment, PostgreSQL
migration, scheduled backups, restore drills and external monitoring to the hosting
environment. [backend/settings.py:188](backend/settings.py#L188) provides a local
Redis URL default; this is a development default, not proof of an exposed broker.

Implement private database/broker networking, restricted service accounts, deployment
secret storage and rotation, separate environment credentials, encrypted backups and
restore drills, monitored TLS, supervised workers and security alerts. Run PostgreSQL
concurrency and permission tests, deployment checks, load tests and a security
acceptance exercise. Inspect the actual edge/proxy configuration and headers. Review
the existing broad HSTS/subdomain/preload configuration against the domain rollout
before enabling it on production infrastructure.

## Medium priority — before launch or in the first hardening release

### S04 — Make abuse controls consistent and proxy-aware

Evidence: [customer_services/security.py:44](customer_services/security.py#L44) keys
rate buckets on `REMOTE_ADDR`. [deploy/nginx.conf.example:21](deploy/nginx.conf.example#L21)
proxies to loopback and supplies client-IP headers, but the application limiter does
not consume a validated forwarded address. [logistics/views.py:28](logistics/views.py#L28)
and [logistics/views.py:47](logistics/views.py#L47) have no visible equivalent throttling
for quotation/contact intake. Staff login also lacks an IP-level limit.

Implement edge limits and account/IP-aware application limits, trusting client IP
metadata only from a configured proxy. Otherwise many users can share the proxy's
bucket, allowing one client to exhaust a public service's quota. Add bounded cleanup,
request-size limits and monitoring. Verify hosting controls rather than assuming none.

### S05 — Add a tested Content Security Policy

Evidence: [backend/settings.py:77](backend/settings.py#L77) has no CSP middleware;
[deploy/nginx.conf.example](deploy/nginx.conf.example) has no CSP header.
[templates/dashboard/base_dashboard.html:8](templates/dashboard/base_dashboard.html#L8)
contains an inline theme script. An unseen hosting edge may supply a policy.

Deploy CSP in report-only mode first, inventory trusted asset origins, move or nonce
inline scripts, then enforce a restrictive policy. This is defense in depth against
script injection; this review did not establish an exploitable XSS path.

### S06 — Strengthen handling of uploaded documents

Evidence: [operations/services.py:199](operations/services.py#L199) validates a 5 MB
limit, supported images and parsed PDFs. It returns the original bytes and does not
perform malware scanning/quarantine. Proof downloads already require authorization
and use attachment responses. The nginx example blocks public employee media.

Add quarantine and malware scanning before document release, maintain parser patches,
and define retention and safe download procedures. Implement a protected employee
photo delivery path before exposing that media. Parsing a valid PDF is not equivalent
to proving its contents harmless; this is an additional protection, not a finding of
publicly exposed delivery proof files.

### S07 — Harden privileged sessions

Evidence: [accounts/views.py:36](accounts/views.py#L36) permits a 30-day remembered
staff session; no dedicated idle timeout or privileged reauthentication policy is
visible in the reviewed settings/views.

Define shorter privileged session lifetimes, idle expiry, reauthentication for
sensitive account/security/payment operations, session revocation and access review
procedures. Keep ordinary workflow authorization checks on every request.

### S08 — Add independent audit protection and operational detection

Evidence: [core/models.py:118](core/models.py#L118) and
[operations/models.py:130](operations/models.py#L130) enforce append-only writes at
the Python layer. [DEPLOYMENT.md:65](DEPLOYMENT.md#L65) states that external monitoring
is not configured. Application guards do not prevent privileged database alteration.

Add audited login/security/permission changes, centralized redacted logs, alerts for
failed authentication and suspicious exports/payment activity, separate audit storage
or database privileges, retention/access policies and an incident-response runbook.
Restrict logs containing personal data; never log credentials or recovery tokens.

### S09 — Automate dependency and secret checks

Evidence: [requirements-production.txt:2](requirements-production.txt#L2) uses version
ranges for PostgreSQL/server dependencies. Local package pins do not establish an
automated vulnerability scan or reproducible full dependency closure.

Create a reproducible dependency lock, CI dependency/advisory and secret scanning,
and a patch process for Django, PDF/image parsers and frontend assets. Scan repository
history before sharing sensitive deployments. This review did not establish that a
specific pinned package is vulnerable.

## Existing controls to preserve and validate

- Customer ownership filtering and whitelist-only public tracking.
- CSRF protection on browser actions; narrowly scoped provider callbacks.
- Server-side permission checks and separate Admin approvals.
- Gateway API readback verification of reference, amount and currency; idempotent posting.
- TLS/host restrictions for outbound integrations, bounded requests and redacted errors.
- Authenticated proof downloads and export auditing.

Validate real merchant callbacks, provider permissions, signing/shared secrets,
duplicate/reordered events and secret rotation in sandbox. These are acceptance work
for existing integrations, not a recommendation to replace verification with callback trust.

Guidance: [Django security](https://docs.djangoproject.com/en/6.0/topics/security/)
and [deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/).

Recommended order: S01/S04, access policy S02, production gate S03, then S05–S09
before expanding external access. No application code was changed by this review.
