# Deployment baseline

This repository provides guarded configuration and example server configuration.
A live production deployment, PostgreSQL migration from SQLite, scheduled backups,
restore drills, and external monitoring still require an actual hosting environment.

## Configuration

Install `requirements-production.txt`. Export the environment variables shown in
`.env.example` using the hosting platform's secret manager; the file is not loaded
automatically. DEBUG defaults to false. Startup rejects missing/short development
secrets, absent/wildcard hosts, SQLite in production, and missing database credentials.
Use a unique random secret with at least 50 characters. Never reuse the local key.

The default PostgreSQL TLS mode is `verify-full`. Configure the server CA using
libpq's `PGSSLROOTCERT` when necessary. A private local database may use an explicitly
chosen SSL mode appropriate to the host; do not disable verification for a remote
database. Provision a dedicated, least-privileged application database user.

Production rollout:

1. Back up the existing database and uploaded media. If converting from SQLite,
   perform and validate a separate data migration before switching the application.
2. Install dependencies and configure the production variables.
3. Run `python manage.py check --deploy --fail-level WARNING`.
4. Run `python manage.py migrate` and `python manage.py seed_roles`.
5. Run `python manage.py collectstatic --noinput`.
6. Start `gunicorn backend.wsgi:application --config deploy/gunicorn.conf.py` on Linux.
7. Configure the reverse proxy using `deploy/nginx.conf.example` as a starting point.
   Set the real hostname, certificates, paths, and service supervision.
8. Verify login, authorized/denied workflows, CSRF submissions, static assets, HTTPS
   redirect, cookies and database connectivity in staging before cutover.

The new employee migration preserves IDs, initializes counters from existing IDs,
and changes blank phone numbers to NULL. Multiple employees can omit phone numbers.
Take a database backup before applying it; restoring that backup is the safe rollback
if the previous schema cannot represent multiple missing phone numbers.

## Static files, uploads, and proxies

STATIC_ROOT is `staticfiles/`; nginx serves collected assets. The example blocks
public media access because employee photographs may be private. An authenticated
media delivery design is still required before exposing uploads. Never allow uploaded
content to execute. Persist media independently of an application release.

Set DJANGO_TRUST_PROXY=true only when your trusted proxy overwrites incoming
X-Forwarded-Proto and clients cannot bypass the proxy to access the application port.
The example nginx does both when deployed with a loopback-only application listener.
Use DJANGO_CSRF_TRUSTED_ORIGINS for the actual HTTPS origins where required.

## Backups and monitoring

Configure scheduled PostgreSQL custom-format dumps (`pg_dump --format=custom`)
using credentials from a protected service account. Store encrypted, access-controlled,
off-site copies with a retention policy. Include uploaded media and necessary recovery
configuration. Validate restoration with `pg_restore` into an isolated database before
launch and periodically afterwards; never test a restore against the live database.
SQLite backups alone do not verify PostgreSQL disaster recovery.

Django and Gunicorn write errors/access logs to stderr/stdout for collection by the
hosting platform. Set log retention and alert on 5xx rates, failed health probes,
database availability, storage capacity and failed/overdue backups. An external
HTTPS probe of `/accounts/login/` confirms web serving; use a restricted application
probe that reads the database to verify database readiness. Logging is not an immutable
business audit trail and no external monitoring service is configured by this patch.

## Permission rollout

`seed_roles` adds defaults while preserving existing custom grants and memberships.
Review existing grants before production; seeding deliberately does not revoke them.
Model-level permissions cover the current organization. Tenant/branch ownership,
separate approval authority, least-privilege access to form choices, and administrator
lockout policy require further design and testing before broader deployment.
