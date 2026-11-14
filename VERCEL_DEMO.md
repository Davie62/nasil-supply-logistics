# Temporary NASIL client demo on Vercel

Target project: `tech-sprite/nasil-supply-logistics`. Deploy to **Preview** using
`--environment preview`, without `--prod` or the deprecated `--target` flag.
The Django framework preset discovers `manage.py`, loads
`backend.wsgi.application`, runs `collectstatic` and serves static files from the
Vercel CDN. Python is pinned to 3.13. Do not restore the old `myproject/wsgi.py`
legacy builder configuration.

## Preview environment

Configure these in Vercel project Settings > Environment Variables, targeting
Preview. Keep credentials out of Git and chat. Use an isolated demo database or
schema with synthetic records when clients will create or change records.

| Variable | Value or purpose |
| --- | --- |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | Stable private random key, at least 50 characters |
| `SECURITY_ENCRYPTION_KEYS` | Separate stable Fernet key ring; do not replace an existing ring without rotation |
| `DJANGO_DB_ENGINE` | `postgresql` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Hosted database endpoint and port |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Demo database credentials |
| `POSTGRES_DATABASE` | Neon-provided alternative to `POSTGRES_DB`; either is accepted |
| `POSTGRES_SSLMODE` | `verify-full` |
| `CELERY_BROKER_URL` | Hosted Redis TLS connection URL, starting with `rediss://` |
| `SECURITY_REQUIRE_STAFF_MFA` | `true` |
| `NOTIFICATIONS_DELIVERY_ENABLED` | `false` for the initial demo |
| `INTEGRATIONS_DELIVERY_ENABLED` | `false` for the initial demo |
| `DJANGO_ALLOWED_HOSTS` | Additional exact custom/alias hostnames, if any |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Additional exact HTTPS origins, if any |
| `PUBLIC_SITE_URL` | Actual canonical demo HTTPS URL once assigned |

Vercel must expose its system environment variables. Only when `VERCEL=1`, Django
adds the exact platform-supplied deployment, branch and project hostnames to host
and CSRF allowlists, and recognizes Vercel's forwarded HTTPS protocol. No global
`*.vercel.app` trust is enabled. Leave generic `DJANGO_TRUST_PROXY=false`; the
Vercel-specific HTTPS configuration does not require trusting arbitrary peer IPs.

## Deployment and database setup

1. Sign in with `npx vercel login` and link the intended project with
   `npx vercel link --project nasil-supply-logistics` (select the correct team).
2. Confirm the required Preview environment variable **names** using
   `npx vercel env ls preview`. Do not paste secret values into chat or logs.
3. Install the project dependencies in a trusted environment with the demo
   database variables configured. Back up any existing hosted records, inspect
   `python manage.py migrate --plan`, then apply `python manage.py migrate` and
   `python manage.py seed_roles`. Create a dedicated staff demo account and enroll
   its authenticator. Do not share a production superuser account with clients.
4. Deploy with `npx vercel deploy --environment preview`. Automatic database migrations, real message
   delivery and financial transactions are deliberately absent from the build.
5. Share the Preview URL and, if Vercel deployment protection requires it, arrange
   client access through Vercel's sharing controls without disabling app login.

`.vercelignore` excludes local secrets, SQLite, backups, uploaded media, virtual
environments and QA artifacts from CLI uploads. The local SQLite data is not
copied to the hosted database. No custom `vercel.json` builder override is used;
Vercel should discover this Django project from the root `manage.py`.

## Demonstration limits

- Proof-of-delivery bytes are stored in the database and are available through
  permission-checked downloads. Logos and staff photos use local media storage;
  configure private persistent object storage before relying on those uploads.
- Redis alone does not start the existing Celery worker or beat scheduler. Run
  those separately or integrate a supported queue deployment before enabling
  transactional delivery. Existing integration jobs remain queued with delivery
  disabled.
- PostgreSQL migrations and test/demo records are a separate rollout step. A
  successful web build does not establish that the database schema is current.
- This guide and local configuration do not constitute a successful deployment;
  retain the actual Vercel build result and generated URL before sharing a demo.

References: [Django on Vercel](https://vercel.com/docs/frameworks/full-stack/django),
[Vercel request headers](https://vercel.com/docs/headers/request-headers).

## Current rollout: 27 October 2026

- Historical Preview build on 27 October: **READY**, deployment `dpl_4rRjDboynk4C85Pq6EV3eRYUP9yT`.
- URL: https://nasil-supply-logistics-2ozodjkdn-tech-sprite.vercel.app
- Vercel Authentication remains enabled; use a deployment-specific share link for
  external client access. Do not place share tokens or passwords in this document.
- Free Neon resource `nasil-demo-postgres`: new empty database verified over TLS,
  Django migrations applied, sample organization and roles initialized.
- Free Upstash resource `nasil-demo-redis`: paid auto-upgrade disabled; TLS PING
  passed and the broker secret is configured for Preview.
- Dedicated Administrator-role staff account: `nasil-demo-admin`. Password is in
  the ignored local file `.local/vercel-demo-access.txt`. MFA enrollment is required
  at first sign-in. No local customer data was imported.
- Nine deployment configuration tests passed. Vercel completed dependency
  installation, Django discovery, static collection and function bundling.
- The application URL was not fetched as part of rollout verification; the READY
  result establishes build/deployment completion, not end-to-end browser acceptance.
