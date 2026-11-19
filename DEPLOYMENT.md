# Deployment baseline

This repository provides guarded configuration and example server configuration.
A live production deployment, PostgreSQL migration from SQLite, and external
monitoring still require an actual hosting environment. Encrypted backup/restore
commands, health probes and systemd units are included, but their schedules and
restore drills must be exercised on the real host.

## Configuration

Install `requirements-production.txt`. Export the environment variables shown in
`.env.example` using the hosting platform's secret manager. A local `.env` is
loaded automatically when present, but real environment variables always win.
DEBUG defaults to false. Startup rejects missing/short development
secrets, absent/wildcard hosts, SQLite in production, and missing database credentials.
Use a unique random secret with at least 50 characters. Never reuse the local key.
Also supply a separate SECURITY_ENCRYPTION_KEYS key ring and a rediss:// broker.
Production staff MFA and verified PostgreSQL/broker TLS are enforced at startup.
See SECURITY_IMPLEMENTATION.md for enrollment, key rotation and incident recovery.

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

## Container image

`Dockerfile` builds the production image (Gunicorn, non-root user) from
`requirements-production.txt`. `docker-compose.yml` is a local development stack
only: it runs with `DJANGO_DEBUG=true` and plain HTTP. Do not deploy the compose
file as-is; run the image with the production environment variables and a
TLS-terminating reverse proxy.

## Static files, uploads, and proxies

STATIC_ROOT is `staticfiles/`; nginx serves collected assets. Uploaded media
(employee photographs and company logos) is private, so production uses S3 through
`django-storages` and serves files only through short-lived presigned URLs. The
storage backend never sets a public ACL and never overwrites an existing object.
Set `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME` and, for S3-compatible services,
`AWS_S3_ENDPOINT_URL`. Prefer an instance role over static access keys. Keep the
bucket private and block public access at the account level. `AWS_QUERYSTRING_EXPIRE`
defaults to 300 seconds and must stay between 60 and 3600.

`MEDIA_STORAGE_BACKEND=filesystem` is the development default. Outside DEBUG it is
rejected unless `MEDIA_STORAGE_ALLOW_EPHEMERAL=true` is also set; that combination
is only for a disposable demo and loses uploads when the release is replaced.
Never allow uploaded content to execute. Persist media independently of an
application release and include the bucket in the backup policy.

Set DJANGO_TRUST_PROXY=true only when your trusted proxy overwrites incoming
X-Forwarded-Proto and clients cannot bypass the proxy to access the application port.
The example nginx does both when deployed with a loopback-only application listener.
Use DJANGO_CSRF_TRUSTED_ORIGINS for the actual HTTPS origins where required.
Set SECURITY_TRUSTED_PROXY_NETWORKS to the proxy's actual peer networks (for the
loopback example: 127.0.0.1/32,::1/128). X-Real-IP is trusted only from those peers.
HSTS is opt-in after real HTTPS validation; decide its scope before enabling it.

## Backups and monitoring

Backups are produced by `python manage.py backup_database`. The command uses
`pg_dump --format=custom`, encrypts the dump with the `SECURITY_ENCRYPTION_KEYS`
ring, writes a SHA-256 manifest next to it, and prunes copies beyond
`BACKUP_RETENTION_COUNT`. Set `BACKUP_DIRECTORY` to a durable, access-controlled
path outside the release directory (for example `/var/backups/nasil`) and copy
it off-site. The key ring is required to read the backup: losing every key makes
the archives unrecoverable, so escrow the keys separately from the backups.

`deploy/systemd/nasil-backup.service` and `nasil-backup.timer` run the command
daily at 01:15 UTC with a randomised delay and `Persistent=true`. Confirm with
`systemctl list-timers nasil-backup.timer`.

Restore drills use `python manage.py restore_database <file> --target-database
<isolated-db> --confirm`, which verifies the manifest checksum, decrypts into a
temporary file and refuses to touch the live database. Restore into a separate
database or SQLite file, start the application against it, run
`manage.py check` and the regression suite, and compare record counts before
promoting. Never test a restore against the live database. A backup that has
never been restored is an assumption, not a recovery plan.

Django and Gunicorn write errors/access logs to stderr/stdout for collection by
the hosting platform. Set log retention and alert on 5xx rates, failed health
probes, database availability, storage capacity and failed/overdue backups. An
external HTTPS probe of `/healthz` confirms web serving; `/readyz` checks the
database and, when `HEALTHCHECK_BROKER=true`, the broker.
`python manage.py check_operational_health --strict` additionally checks
unapplied migrations, media-storage write/read access, broker connectivity and
backup freshness (`BACKUP_MAX_AGE_HOURS`). `nasil-health.timer` runs it every
15 minutes; a failed unit is the alerting signal. Logging is not an immutable
business audit trail and no external monitoring service is configured by this
patch.

## Process supervision

Run exactly one `celery beat` process and one or more workers. Two schedulers
duplicate every periodic task, including outbox delivery and provider dispatch.
The units in `deploy/systemd/` supervise Gunicorn (`nasil-web`), the worker
(`nasil-worker`) and beat (`nasil-beat`); beat keeps its schedule in
`/var/lib/nasil/celerybeat-schedule` so a restart does not replay overdue tasks.
Workers use `acks_late`, so stop them with SIGTERM and allow up to
`TimeoutStopSec` for in-flight tasks. `docker-compose.yml` mirrors the same
restart and persistence rules for local use.

## Permission rollout

`seed_roles` adds defaults while preserving existing custom grants and memberships.
Review existing grants before production; seeding deliberately does not revoke them.
Model-level permissions cover the current organization. Tenant/branch ownership,
separate approval authority, least-privilege access to form choices, and administrator
lockout policy require further design and testing before broader deployment.
