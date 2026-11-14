# NASIL security safeguards

Security code lives in the Django app `security_controls`. Production startup
requires private secrets, verified PostgreSQL TLS, a `rediss://` Celery broker and
mandatory staff MFA. Local HTTP development remains supported.

## Authentication and account recovery

`GuardedModelBackend` applies one atomic account lockout policy to staff, customer
and Django admin password authentication: five failed attempts lock the account
for 30 minutes. Login requests also have IP-based limits. New passwords must pass
Django's similarity/common/numeric checks and have at least 12 characters. Existing
passwords are not changed automatically. Passwords are one-way hashed by Django;
they are never reversibly encrypted or displayed.

Staff MFA is mandatory in production. Development defaults to optional enrollment;
set `SECURITY_REQUIRE_STAFF_MFA=true` on a local server to enforce enrollment there.
Once a user enrolls, their MFA is enforced in every environment, including Django
admin. Customers can opt in from **Preferences → Account security**. Staff use the
account menu. Anonymous requests still follow the normal login requirements.

After the password step, protected requests are gated until authenticator enrollment
or verification completes. Scan the locally generated QR code with a TOTP app, enter
a code, and securely save ten recovery codes. Secrets are Fernet-encrypted; recovery
codes are hashed, single-use and shown only during enrollment. TOTP counters prevent
replay. Five invalid MFA attempts lock verification for 15 minutes. Enrollment keys
expire after ten minutes; QR images and security pages are private/non-cacheable.

Lost all factors: an authorized host operator must independently verify the account
owner and record the recovery ticket, then run:

```powershell
python manage.py reset_mfa --username STAFF_USERNAME --reason "Verified recovery ticket SEC-123"
```

This removes factors, revokes existing sessions and records a security alert. It is
not an HTTP/admin bypass endpoint. Production staff must enroll again at next login.

## Sessions and permissions

Staff sessions have an eight-hour absolute cap and 30-minute inactivity limit;
customers have a 24-hour absolute cap and one-hour inactivity limit. Without
**Remember me**, the cookie also expires when the browser closes. Remembered sessions
remain subject to these limits. MFA verification rotates the session key.
**Account security → Sign out all devices** requires the current password and revokes
other sessions on their next request. Existing password-reset session invalidation
is retained. Permission changes invalidate prior MFA verification.

Existing staff/model permissions, customer ownership filters, maker/approver
separation, guarded business services and private document checks remain active.
Staff authorization is organization-wide; branch isolation still requires an agreed
policy and object/queryset implementation. Do not mistake MFA for object authorization.

## Request validation and browser controls

`RequestGuardMiddleware` limits query length/count, rejects duplicate query keys,
control characters, oversized search terms and invalid page/staff identifiers.
Form bodies have structural/text bounds; existing Django forms still validate field
types, relationships, choices and business rules. Commercial reports reject unknown
filter names. `strict_json()` rejects duplicate keys, non-object payloads, non-finite
numbers and excessive nesting/size; the gateway callback reuses it.

SQL-looking text remains data passed through Django ORM parameters. Templates retain
automatic output escaping; legitimate apostrophes and multiline descriptions are
not destructively stripped. New APIs must reuse typed Forms and workflow services.

CSRF middleware remains enabled. Only the authenticated provider callback is exempt;
its body cannot post money directly and always triggers provider API verification.
Every HTML response receives a nonce-based script CSP, `object-src 'none'`, same-origin
form/base restrictions and frame protection. Script `unsafe-inline`/`unsafe-eval` are
not permitted. Inline styles remain allowed for the existing theme. Public third-party
plugins still require ongoing compatibility and security review.

## Encryption, TLS and configuration

Production environment example (values are placeholders):

```text
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<private-random-signing-key>
DJANGO_ALLOWED_HOSTS=<actual-hostname>
SECURITY_ENCRYPTION_KEYS=<newest-fernet-key>,<previous-key-during-rotation>
SECURITY_REQUIRE_STAFF_MFA=true
POSTGRES_SSLMODE=verify-full
CELERY_BROKER_URL=rediss://<private-broker>:6379/0
DJANGO_TRUST_PROXY=true
SECURITY_TRUSTED_PROXY_NETWORKS=127.0.0.1/32,::1/128
```

Generate Fernet keys with `cryptography.fernet.Fernet.generate_key()` in a protected
operator environment and store them in the deployment secret manager. Never commit
them or use the Django signing key as an encryption key. Development generates
independent random keys under ignored `.local/`; restrict that directory's OS access.
Back up required keys separately and securely. Django does not load `.env` files.

For rotation, prepend the new environment key, retain previous keys, and run
`python manage.py rotate_security_keys`. Retain old keys until all encrypted session
values and relevant backups have expired or been migrated. The command never prints
secret values. API credentials continue to use environment references, not database
plaintext or browser JavaScript. PostgreSQL disk/media/backups encryption and vault
encryption are hosting controls: this code does not configure or prove them.

HTTPS redirect and secure/HttpOnly/SameSite cookies are enforced outside DEBUG. Use
the supplied nginx TLS proxy and overwrite incoming client IP/proto headers. Trust
only configured proxy peers; direct client-supplied IP headers are ignored. HSTS is
operator opt-in after validating actual certificates/domains; preload and broad
subdomain policies are not automatically enabled.

## Logging, detection and operational alerts

The `nasil.security` logger emits structured JSON to stdout/stderr for a centralized
collector. Production application logs use a metadata-only JSON formatter. Credentials,
raw messages/bodies, query strings, cookies, OTPs, email addresses and exception text
are not serialized by this formatter. Events use request UUIDs, route names, user IDs
and keyed IP fingerprints. Django sensitive-post/variable annotations protect auth
failure reports as well.

`SecurityEvent` records login failures, factor verification/recovery, logout, session
expiry/revocation, denied requests and permission changes. Repeated suspicious events
create a deduplicated `SecurityAlert`; permission changes, factor recovery and operator
reset are immediately flagged. Superusers can inspect read-only events/alerts in
Django admin. No raw passwords, keys, recovery codes or tokens belong in events.
Forward JSON `security_alert` records to the hosting alert service for paging/email;
external forwarding is not configured or sent by this implementation.

Audit records are append-only through application/ORM APIs. An independent collector,
restricted database privileges, retention/cleanup jobs and protected backups are still
required to resist privileged database changes and control storage growth.

## Reusable examples

```python
from security_controls.crypto import encrypt_secret, decrypt_secret
from security_controls.validators import clean_text, strict_json
from security_controls.events import security_event

protected = encrypt_secret(value_to_protect)  # For decryptable secrets, not passwords.
value = decrypt_secret(protected)
payload = strict_json(request.body, allowed_fields={"invoice_id", "provider"},
                      required_fields={"invoice_id", "provider"})
# Next validate types/choices with a Django Form and enforce ownership/permissions.
name = clean_text(form.cleaned_data["name"], limit=200, multiline=False)
security_event("permission_denied", request=request, level="warning")
```

```python
MIDDLEWARE = [
    "security_controls.middleware.RequestGuardMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "security_controls.middleware.AuthenticationGuardMiddleware",
    # Messages and clickjacking middleware follow, as in backend/settings.py.
]
```

## Verification and deployment gate

Run `python scripts/security_scan.py`, Django system/migration checks, the full test
suite, and `python -m pip_audit --vulnerability-service osv --timeout 60`. The source
scanner detects high-confidence credential patterns, unsafe execution/HTML calls,
interpolated SQL outside migrations/tests and inline scripts without nonces. It never
prints suspected secret values and is not a complete vulnerability or history scanner.
GitHub Actions configures these checks with read-only permissions and pinned actions;
Dependabot checks Python dependencies and Actions weekly. Remote CI has not run until
these changes are pushed. PostgreSQL concurrency, Linux deployment, real TLS/proxy,
encrypted storage, key recovery, provider sandbox and monitoring acceptance remain
required before production. See `security_best_practices_report.md` for the app inventory.

Local verification on 27 October 2026: 205 full-suite tests (201 passed, four
PostgreSQL-only skips); final security/accounts/configuration checks: 40 tests
(39 passed, one PostgreSQL skip). Migration/source checks passed, and the installed
Windows dependency audit found no known advisories. Security migrations were applied
with a verified backup and preservation checks across 54 existing tables. Browser
QA used a separate database and synthetic user for MFA enrollment, recovery and
session revocation. Production HSTS subdomain/preload checks deliberately warn until
the operator has verified HTTPS coverage and enabled those policies.
