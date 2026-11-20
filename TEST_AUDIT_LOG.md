# NASIL Supply & Logistics — Test and Security Assurance Log

## Document control

| Field | Value |
| --- | --- |
| Document ID | NASIL-TST-2026-11-16 |
| Title | Test Execution and Security Assurance Log |
| Version | 1.6 |
| Status | Phase 3 complete (operational readiness); remote CI green; awaiting engineering sign-off |
| Date of record | 2026-11-16 (initial), 2026-11-18 (rerun), 2026-11-19 (Phase 3, final verification and remote CI remediation) |
| Classification | Internal — Engineering |
| Repository | `Davie62/nasil-supply-logistics` |
| Branch | `development` |
| Baseline commit | `2055a73` (Phase 2) plus the Phase 3 change set recorded in §11.2 |
| Application | NASIL supply, logistics, commercial and finance monolith |
| Test framework | Django 6.1.2 test runner (`manage.py test`) |
| Assurance tooling | `coverage.py` 7.17.3, `ruff` 0.17.5, `moto` 5.2.5, Django system checks, migration drift check |
| Continuous integration | GitHub Actions — `.github/workflows/security.yml` |
| Prepared by | QA / application-security review (AI-assisted) |
| Reviewed by | Engineering lead — **pending** |
| Approval | **Not yet approved for production acceptance** |

This log is the single dated record of test execution and results for the
application. New entries are appended by date; earlier entries are never
rewritten except to correct a factual error, which is noted in the change log.

---

## 1. Purpose and authority

This document records what was tested, how it was tested, what passed, what
failed, and what residual risk remains. It supports the phased remediation of
the architecture findings in `PROJECT_STATUS_REVIEW.md`, covering the P2
automation gap (*"PostgreSQL/browser CI coverage is incomplete"*) and the P1
operational-readiness gaps (private media, supervised workers, backups and
monitoring).

The log is evidence of local and CI-configured regression testing. It is **not**
a penetration-test report, a production acceptance certificate, or proof that
live provider integrations, infrastructure, or operational controls work.

---

## 2. Scope

### 2.1 In scope

- Order lifecycle, totals, stock reservation, fulfillment, dispatch and closure.
- Catalogue products, stock levels, warehouse guards, reservations and stock moves.
- Supplier audits, procurement requests, purchase orders, budgets and goods receipts.
- Fleet vehicle/driver readiness, assignments, checkpoints and maintenance.
- Payment ledger, reversals, statement import, matching and reconciliation.
- Authorization boundaries, workflow-bypass controls, idempotency and immutability.
- Full existing regression suite and static checks.

### 2.2 Out of scope

- Live SendGrid, Twilio, Africa's Talking, Odoo, Flutterwave or pawaPay traffic.
- Browser end-to-end journeys and visual/accessibility acceptance.
- Load, stress, soak and performance testing.
- Database migration rehearsal against production data.
- Live infrastructure provisioning: a real S3 bucket, a real PostgreSQL
  `pg_restore` target, systemd supervision and an external monitoring service.
- Formal penetration testing or third-party security assessment.

### 2.3 Phase 3 scope (added 2026-11-19)

Phase 3 covers the operational-readiness controls that can be verified in code
and in a disposable local environment:

- Durable, private media storage: S3 backend selection, fail-closed production
  configuration, presigned URLs, no public ACLs, no overwrite.
- Worker and beat supervision: systemd units, compose restart/persistence,
  schedule integrity.
- Encrypted database backup and restore: streaming encryption, manifests,
  checksums, retention, refusal to touch the live database.
- Operational health probe: database, migrations, broker, media storage and
  backup freshness.
- A local backup/restore drill proving a byte-identical SQLite round trip.

---

## 3. Environment and tooling

| Component | Local execution | CI execution |
| --- | --- | --- |
| Operating system | Windows (win32) | Ubuntu latest; Windows latest |
| Python | 3.13 | 3.13 |
| Django | 6.0 | 6.0 |
| Database | SQLite (`DJANGO_DEBUG=true`) | PostgreSQL 17 (Linux); SQLite (Windows) |
| Broker | Not required for tests | Redis 7 (Linux) |
| Test runner | `venv/Scripts/python.exe manage.py test` | `python manage.py test` |
| Coverage | `coverage run manage.py test` | `coverage run` + `coverage report` (85% gate) |
| Object storage | `moto` 5.2.5 in-process S3 mock | `moto` 5.2.5 in-process S3 mock |
| Lint | `ruff check .` | `ruff check .` |

The Linux CI job now provisions PostgreSQL 17 and Redis 7 as service
containers, runs the suite against PostgreSQL, and enforces a coverage
threshold. The Windows job keeps SQLite to preserve cross-platform
compatibility. Four PostgreSQL-only concurrency checks are skipped on SQLite
and execute on the Linux job.

---

## 4. Methodology and evidence standard

1. **Service-level integration tests.** Each test exercises the real workflow
   service, database constraints, permissions and audit side effects; it does
   not call private helpers or assert on implementation details alone.
2. **Negative-path first.** Every control is tested with a valid path and at
   least one invalid path (wrong actor, stale version, missing reason,
   over-limit amount, duplicate key, terminal state).
3. **Separation of duties.** A non-superuser `maker` performs preparation; a
   different superuser `approver` performs approvals. A staff `outsider`
   without grants verifies permission denial.
4. **Bypass resistance.** Direct `.save()`, `QuerySet.update()` and
   `bulk_update()` are asserted to raise `ValidationError`.
5. **Evidence retention.** Command output, test counts and coverage are
   recorded by date in §7 and §8. CI configuration is version-controlled.
6. **No production data.** All tests run against disposable test databases.

### 4.1 Shared fixture

`core/test_commercial_fixtures.py` provides `CommercialFixtureMixin`:

- `maker` — staff user with explicit commercial grants;
- `approver` — different superuser for approval separation;
- `outsider` — staff user with no grants;
- company, branch, department, warehouse, product, stock level and opening stock;
- an approved quotation and pending shipment (`booked_shipment`).

This removes duplicated setup and keeps the five new suites focused on
behaviour.

---

## 5. Test inventory

Counts are test methods. "Result" reflects the final 2026-11-19 verification run.

| Suite | File | Tests | Primary controls | Result |
| --- | --- | ---: | --- | --- |
| Accounts (incl. concurrency) | `accounts/tests.py`, `accounts/test_concurrency.py` | 12 | Authentication, lockout, MFA, employee lifecycle, PostgreSQL row locks | Pass / 1 skipped on SQLite |
| **Backend configuration (new)** | `backend/test_settings.py` | **17** | Fail-closed settings, TLS, PostgreSQL requirement, media/backup policy | **Pass** |
| **Backend scheduling (new)** | `backend/test_celery.py` | **3** | Beat entries resolve to registered tasks, no duplicates, sane cadence | **Pass** |
| **Core storage (new)** | `core/test_storage.py` | **5** | S3 private ACLs, presigned URLs, prefix, overwrite policy | **Pass** |
| **Core backup (new)** | `core/test_backup.py` | **38** | Encryption, manifests, checksums, retention, backup/restore commands, health probe | **Pass** |
| Core business rules | `core/test_business_rules.py`, `core/tests.py` | 34 | Pricing, approvals, workflow guards, audit | Pass |
| Core health | `core/test_health.py` | 6 | `/healthz`, `/readyz`, broker probe | Pass |
| Core workflow concurrency | `core/test_workflow_concurrency.py` | 2 | Version and lock behaviour | Pass / PostgreSQL-gated |
| Customer services | `customer_services/tests.py`, `test_registration.py` | 49 | Registration, verification, portal ownership, recovery | Pass |
| Customers | `customers/tests.py` | 1 | Customer CRUD permission boundary | Pass |
| Dashboard | `dashboard/tests.py` | 14 | Metrics, navigation context, permissions | Pass |
| Integrations | `integrations/tests.py` | 9 | Odoo/Flutterwave/pawaPay adapters and retries | Pass |
| Logistics | `logistics/tests.py` | 5 | Public intake and carrier management | Pass |
| Operations | `operations/tests.py`, `test_commercial.py`, `test_concurrency.py`, `test_mobile_ui.py` | 55 | Stock ledger, proofs, settings, staff, commercial flows, mobile UI | Pass / 1 skipped on SQLite |
| Organization | `organization/tests.py` | 0 | No dedicated tests (admin-backed) | n/a |
| Payments | `payments/tests.py` | 0 | No dedicated tests (covered via finance and customer services) | n/a |
| Quotations | `quotations/tests.py` | 1 | Quotation workflow regression | Pass |
| Security controls | `security_controls/tests.py` | 22 | MFA, sessions, request validation, alerts | Pass |
| Shipments | `shipments/tests.py` | 1 | Shipment workflow regression | Pass |
| **Orders (new)** | `orders/tests.py` | **10** | Totals, approval separation, reservation, fulfillment, dispatch, closure, bypass | **Pass** |
| **Inventory (new)** | `inventory/tests.py` | **9** | SKU/unit locks, archive guards, reservations, adjustments, bypass | **Pass** |
| **Procurement (new)** | `procurement/tests.py` | **11** | Supplier audit gating, budgets, approvals, receipts, cancellation | **Pass** |
| **Fleet (new)** | `fleet/tests.py` | **11** | Vehicle/driver readiness, exclusivity, checkpoints, maintenance | **Pass** |
| **Finance (new)** | `finance/tests.py` | **12** | Payments, reversals, statements, matching, reconciliation | **Pass** |
| **Total** | | **327** | | **323 passed, 4 skipped, 0 failed** |

---

## 6. Phase 2 — detailed results by application

### 6.1 Orders (`orders/tests.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Order totals must match the approved quotation before submission | Pass |
| 2 | Approval requires a different administrator and reserves stock | Pass |
| 3 | Insufficient stock blocks approval without partial reservation | Pass |
| 4 | Fulfillment consumes reserved stock once and creates a shipment | Pass |
| 5 | Cancellation requires a reason and releases reservations | Pass |
| 6 | Dispatch requires fleet assignment; closure requires delivery | Pass |
| 7 | Stale versions and quotation swaps are rejected | Pass |
| 8 | Order lines are locked after submission | Pass |
| 9 | Unsupported fields and unprivileged staff are rejected | Pass |
| 10 | Direct and bulk writes cannot bypass the workflow | Pass |

### 6.2 Inventory (`inventory/tests.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Product SKU is normalized and unique | Pass |
| 2 | SKU and unit are locked once stock exists | Pass |
| 3 | Product/warehouse cannot be archived with open reservations | Pass |
| 4 | Stock links reject a legacy unit mismatch | Pass |
| 5 | Stock adjustment validates quantity, reason and active records | Pass |
| 6 | Reservations account for existing holds | Pass |
| 7 | Release returns reserved stock without consuming it | Pass |
| 8 | Services reject unprivileged staff | Pass |
| 9 | Catalogue balance cannot be written directly | Pass |

### 6.3 Procurement (`procurement/tests.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Purchase order requires a current passing supplier audit | Pass |
| 2 | Request approval requires a separate administrator | Pass |
| 3 | Request is immutable after submission and requires a budget | Pass |
| 4 | Purchase requires an approved request and lines within budget | Pass |
| 5 | Purchase transitions re-check the supplier audit | Pass |
| 6 | Receipt is idempotent and cannot exceed ordered quantity | Pass |
| 7 | Receipt requires a sent purchase order | Pass |
| 8 | Cancellation guards received and paid orders | Pass |
| 9 | Request cancellation requires a reason and no live purchase order | Pass |
| 10 | Procurement services reject unprivileged staff | Pass |
| 11 | Purchase totals are derived from lines | Pass |

### 6.4 Fleet (`fleet/tests.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Vehicle readiness blocks unavailable, due and scheduled-service vehicles | Pass |
| 2 | Driver readiness requires active staff with a current licence and active duty | Pass |
| 3 | Assignment requires a pending shipment and exclusive vehicle/driver/shipment use | Pass |
| 4 | Assignment rejects cargo above vehicle capacity | Pass |
| 5 | Release requires a reason and blocks in-transit assignments | Pass |
| 6 | Released vehicle and driver become available for reassignment | Pass |
| 7 | Checkpoints require transit and valid coordinates | Pass |
| 8 | Vehicle edits guard odometer rollback and active assignments | Pass |
| 9 | Driver edits guard active assignments | Pass |
| 10 | Maintenance completion validates limits and updates the vehicle | Pass |
| 11 | Fleet services reject unprivileged staff | Pass |

### 6.5 Finance (`finance/tests.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Payment requires exactly one customer invoice or supplier order | Pass |
| 2 | Payment validates currency, balance, method, reference, date and voided invoices | Pass |
| 3 | Supplier payments require an approved purchase order | Pass |
| 4 | Payment idempotency and unique provider reference are enforced | Pass |
| 5 | Posted payments are immutable | Pass |
| 6 | Reversal requires admin, reason, unmatched status and non-gateway method | Pass |
| 7 | Balance tracks posted and reversed payments | Pass |
| 8 | Statement import validates header, dates, uniqueness, balance and size | Pass |
| 9 | Matching requires reference, amount, currency and direction | Pass |
| 10 | Reconciliation cannot close with unmatched lines | Pass |
| 11 | Closed reconciliation rejects further matches | Pass |
| 12 | Finance services reject unprivileged staff | Pass |

### 6.6 Phase 3 — operational readiness (2026-11-19)

#### 6.6.1 Durable private media (`core/test_storage.py`)

Tests run against an in-process `moto` S3 mock with the same options the
production settings pass to `S3Storage`.

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Uploads are written under the configured `media/` prefix | Pass |
| 2 | Uploaded objects have no AllUsers or AuthenticatedUsers grant | Pass |
| 3 | `storage.url()` returns a SigV4 presigned URL, not a public URL | Pass |
| 4 | Presigned lifetime follows `AWS_QUERYSTRING_EXPIRE` | Pass |
| 5 | A second upload of the same name never overwrites the first object | Pass |

`backend/test_settings.py` adds:

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Development defaults to filesystem media | Pass |
| 2 | Production without a bucket or region fails closed | Pass |
| 3 | Production selects private S3 with presigned URLs and no custom domain | Pass |
| 4 | Filesystem media outside DEBUG requires explicit ephemeral acknowledgement | Pass |
| 5 | An unsupported media backend is rejected | Pass |
| 6 | Presigned lifetime outside 60–3600 seconds is rejected | Pass |

#### 6.6.2 Worker and beat supervision (`backend/test_celery.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Every `CELERY_BEAT_SCHEDULE` entry resolves to a registered task | Pass |
| 2 | No task is scheduled twice | Pass |
| 3 | Every periodic interval is at least 30 seconds | Pass |

Supervision artefacts are configuration, not executable tests:
`deploy/systemd/nasil-web.service`, `nasil-worker.service`, `nasil-beat.service`,
`nasil-backup.service/.timer`, `nasil-health.service/.timer`; compose adds
`restart: unless-stopped`, a worker `inspect ping` healthcheck, a beat pidfile
healthcheck and a `beatstate` volume for the scheduler clock.

#### 6.6.3 Encrypted backup and restore (`core/test_backup.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | Chunked encryption round-trips a multi-megabyte payload | Pass |
| 2 | A flipped ciphertext bit is rejected | Pass |
| 3 | Decryption with a key outside the ring fails closed | Pass |
| 4 | A non-NASIL file and a truncated block are rejected | Pass |
| 5 | Manifest checksum verification accepts an intact backup | Pass |
| 6 | A modified ciphertext is detected as a checksum mismatch | Pass |
| 7 | Missing manifest and missing backup are rejected | Pass |
| 8 | Backup names are sortable, labelled and validated | Pass |
| 9 | Backup age is computed from the manifest timestamp | Pass |
| 10 | Retention keeps the newest N backups and deletes their manifests | Pass |
| 11 | Retention of zero is rejected | Pass |
| 12 | `backup_database` writes an encrypted file plus manifest | Pass |
| 13 | `backup_database` prunes old copies after writing | Pass |
| 14 | `backup_database` rejects zero retention and dump failures | Pass |
| 15 | `restore_database` refuses to run without `--confirm` | Pass |
| 16 | `restore_database` restores into an isolated target | Pass |
| 17 | `restore_database` refuses the live database | Pass |
| 18 | `restore_database` refuses a tampered backup | Pass |
| 19 | SQLite dump copies the database; a missing file is rejected | Pass |
| 20 | PostgreSQL dump uses `pg_dump --format=custom` and keeps the password out of argv | Pass |
| 21 | Missing `pg_dump`, dump failure and missing `pg_restore` target are reported | Pass |
| 22 | PostgreSQL restore uses `pg_restore --clean --if-exists` | Pass |
| 23 | SQLite restore refuses the live file | Pass |

#### 6.6.4 Operational health probe (`core/test_backup.py`)

| # | Control under test | Result |
| ---: | --- | --- |
| 1 | All-OK results report success | Pass |
| 2 | Any failed probe exits non-zero | Pass |
| 3 | Warnings fail only under `--strict` | Pass |
| 4 | `--skip-storage` does not execute the write probe | Pass |
| 5 | An unexpected probe exception is reported as a failure | Pass |

---

## 7. Execution record by date

### 2026-11-16 — Phase 1 verification (baseline)

| Field | Value |
| --- | --- |
| Command | `DJANGO_DEBUG=true venv/Scripts/python.exe manage.py test --noinput` |
| Result | **220 tests, 216 passed, 4 PostgreSQL-only skipped, 0 failed** |
| Static checks | `manage.py check` clean; `ruff check .` clean; migration drift clean |
| Purpose | Confirm Phase 1 tooling, health probes and dependency split did not regress the suite |

### 2026-11-16 — Phase 2 focused execution

| Field | Value |
| --- | --- |
| Command | `DJANGO_DEBUG=true venv/Scripts/python.exe manage.py test orders inventory procurement fleet finance --noinput` |
| Result | **53 tests, 53 passed, 0 failed** |
| Purpose | Validate the five new application suites before the full regression |

### 2026-11-16 — Phase 2 full regression

| Field | Value |
| --- | --- |
| Command | `DJANGO_DEBUG=true venv/Scripts/python.exe -m coverage run manage.py test --noinput` |
| Result | **273 tests, 269 passed, 4 PostgreSQL-only skipped, 0 failed** |
| Duration | 446 s (coverage instrumentation) |
| Coverage | 87% statement coverage; the `.coverage` data file was not reset before this run, so §8 records the clean 2026-11-18 measurement as authoritative |
| Static checks | `ruff check .` clean; `manage.py check` clean; migration drift clean |
| Purpose | Confirm the new suites integrate with the complete application suite |

### 2026-11-16 — Phase 2 CI configuration (not executed locally)

| Field | Value |
| --- | --- |
| Change | Linux job now runs PostgreSQL 17 + Redis 7 services, installs development dependencies, runs `ruff`, executes the suite under coverage, and enforces the 85% gate from `pyproject.toml` |
| Validation | Workflow YAML parsed successfully; jobs and services enumerated |
| Limitation | Docker is not installed in the local environment, so the containerised CI job was not executed here |
| Result | **Configured; remote execution pending the next push** |

### 2026-11-18 — Phase 2 rerun (clean coverage baseline)

| Field | Value |
| --- | --- |
| Trigger | Full rerun requested after the 2026-11-16 record, to confirm reproducibility |
| Command | `coverage erase && DJANGO_DEBUG=true venv/Scripts/python.exe -m coverage run manage.py test --noinput` |
| Result | **273 tests, 269 passed, 4 PostgreSQL-only skipped, 0 failed** |
| Duration | 582 s (coverage instrumentation) |
| Coverage | **87% (5303 of 6109 statements)**; `coverage report` exit 0 against the 85% gate |
| Static checks | `ruff check .` clean; `manage.py check` clean; `makemigrations --check --dry-run` clean |

**Observation during the rerun.** The first attempt on this date failed one
test: `customer_services.tests.CustomerServicesTests.test_public_tracking_form_supports_ids_and_limits_enumeration`
returned `200` where `429` was expected. The cause was a wall-clock window
boundary inside the 60-request burst, not a product defect — see F-05. The
test now freezes `customer_services.security.timezone.now` for the burst.
After the fix, the single test passed three consecutive isolated runs and the
full suite above passed.

**Reproducibility note.** The rerun began with `coverage erase`; the earlier
2026-11-16 figure was measured over a retained data file. §8 records the
erased run.

### 2026-11-19 — Phase 3 focused execution

| Field | Value |
| --- | --- |
| Command | `DJANGO_DEBUG=true venv/Scripts/python.exe manage.py test backend.test_settings backend.test_celery core.test_storage core.test_backup --noinput` |
| Result | **61 tests, 61 passed, 0 failed** |
| Duration | 7.9 s |
| Composition | 17 deployment-configuration tests, 3 scheduling tests, 5 S3 storage tests, 36 backup/restore/health tests |
| Purpose | Validate the Phase 3 controls before the full regression |

### 2026-11-19 — Phase 3 local operational drill

The drill exercised the shipped commands against a disposable copy of the
development SQLite database. It is evidence that the tooling works end to end,
not evidence that PostgreSQL disaster recovery works.

| Step | Command | Observed result |
| ---: | --- | --- |
| 1 | `manage.py check_operational_health` | database OK, migrations OK, broker SKIP (`HEALTHCHECK_BROKER=false`), storage OK, backup WARN (no backup present) |
| 2 | `manage.py backup_database --output <tmp> --keep 2 --label smoke` | encrypted dump plus manifest written; `engine=sqlite`, 1 228 800 plaintext bytes, 1 638 613 ciphertext bytes |
| 3 | `BACKUP_DIRECTORY=<tmp> manage.py check_operational_health --skip-storage --strict` | all probes OK; newest backup reported 0.0 h old; exit 0 |
| 4 | `manage.py restore_database <backup> --target-path <tmp>/restored.sqlite3 --confirm` | restored into the isolated file |
| 5 | `cmp db.sqlite3 <tmp>/restored.sqlite3` | **byte-identical** |
| 6 | `manage.py restore_database <backup> --target-path <tmp>/restored2.sqlite3` (no `--confirm`) | refused with `CommandError`; no write performed |

**Drill observations.** The first drill attempt exposed F-08 (a `WindowsPath`
value in the manifest payload) after the ciphertext had been written. The
command now stringifies the database name and deletes a partial ciphertext when
manifest writing or pruning fails. A second defect was found in the same pass:
`--output` pointing at an unwritable location raised an unhandled `OSError`; it
now returns a `CommandError` naming the directory.

### 2026-11-19 — Phase 3 full regression (clean coverage baseline)

| Field | Value |
| --- | --- |
| Command | `coverage erase && DJANGO_DEBUG=true venv/Scripts/python.exe -m coverage run manage.py test --noinput` |
| Result | **325 tests, 321 passed, 4 PostgreSQL-only skipped, 0 failed** |
| Duration | 279 s (coverage instrumentation) |
| Coverage | **87% (5637 of 6508 statements)**; `coverage report` exit 0 against the 85% gate |
| Static checks | `ruff check .` clean; `manage.py check` clean; `makemigrations --check --dry-run` clean |
| Change since Phase 2 | +52 tests, +399 measured statements, statement coverage held at 87% while the new operational modules were added |

The 4 skips remain the PostgreSQL-only concurrency checks; they execute in the
Linux CI job and are not a local failure.

### 2026-11-19 — Phase 3 final verification (F-09 remediation)

Final review found that the PostgreSQL restore branch did not refuse the live
database, contrary to the command's documented guarantee (F-09). The guard was
added to both the management command and the backup primitive, with regression
tests for both database engines. The full suite was rerun from an erased
coverage data file after the fix.

| Field | Value |
| --- | --- |
| Focused command | `DJANGO_DEBUG=true venv/Scripts/python.exe manage.py test backend.test_settings backend.test_celery core.test_storage core.test_backup --noinput` |
| Focused result | **63 tests, 63 passed, 0 failed** |
| Full command | `coverage erase && DJANGO_DEBUG=true venv/Scripts/python.exe -m coverage run manage.py test --noinput` |
| Full result | **327 tests, 323 passed, 4 PostgreSQL-only skipped, 0 failed** |
| Duration | 311.8 s (coverage instrumentation) |
| Coverage | **87% (5632 of 6510 statements)**; `coverage report` exit 0 against the 85% gate |
| Static checks | `ruff check .` clean; `manage.py check` clean; `makemigrations --check --dry-run` clean |

### 2026-11-19 — Phase 3 infrastructure configuration (not executed locally)

| Field | Value |
| --- | --- |
| Change | systemd units and timers for web, worker, beat, backup and health probe; compose restart policies, worker `inspect ping` healthcheck, beat pidfile healthcheck and a `beatstate` volume |
| Validation | Unit files reviewed for directive syntax; `docker-compose.yml` parsed with PyYAML — services `beat`, `db`, `migrate`, `redis`, `web`, `worker`; volumes `beatstate`, `pgdata`; worker `restart: unless-stopped`; beat command pins `--schedule=/var/lib/celery/celerybeat-schedule` |
| Limitation | Docker is not installed in the local environment and no systemd host was available, so neither supervision path was started here |
| Result | **Configured; host execution pending staging** |

### 2026-11-19 — Remote CI remediation (PostgreSQL 17 reproduction)

The first three remote CI runs on `development` were red. Because the GitHub
Actions job logs are not readable without repository admin rights, the Linux
job's PostgreSQL 17 condition was reproduced locally with a portable PostgreSQL
17.10 cluster (`initdb`/`pg_ctl`, trust auth, port 55432) and CI-equivalent
environment variables. Redis was not required: every broker check in the suite
is mocked.

Two independent root causes were confirmed and fixed:

1. **Linux job — test-database teardown (F-10).** All four PostgreSQL-only
   concurrency tests passed their assertions, but `DROP DATABASE test_nasil`
   failed with `psycopg.errors.ObjectInUse: database "test_nasil" is being
   accessed by other users` (2 lingering sessions). Each worker thread called
   `close_old_connections()` in its `finally` block, which does **not** close a
   healthy connection; the thread-local connection survived until process exit.
   SQLite tolerated this, PostgreSQL did not. The workers now call
   `connection.close()` directly.
2. **Security job — dependency vulnerability (F-11).** `pip_audit` reported 7
   known CVEs in `pypdf 6.21.2` (CVE-2026-119203/04/05/06/07/08/09), all fixed
   in `6.21.4`. The pin was raised to `6.21.4`, the minimal fixed version that
   keeps the existing `PdfReader` usage unchanged.

| Field | Value |
| --- | --- |
| PostgreSQL reproduction | Portable PostgreSQL 17.10 on 127.0.0.1:55432, `DJANGO_DB_ENGINE=postgresql`, CI-equivalent env; four concurrency tests **4 passed, 0 failed**, test database dropped cleanly (no `ObjectInUse`) |
| Full PostgreSQL command | `DJANGO_DEBUG=true DJANGO_DB_ENGINE=postgresql POSTGRES_DB=nasil POSTGRES_USER=nasil POSTGRES_PASSWORD=nasil POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 POSTGRES_SSLMODE=disable NOTIFICATIONS_DELIVERY_ENABLED=false INTEGRATIONS_DELIVERY_ENABLED=false venv/Scripts/python.exe -m coverage run manage.py test --noinput` |
| Full PostgreSQL result | **327 tests, 327 passed, 0 skipped, 0 failed** — 250.8 s; all four PostgreSQL-only tests now execute and pass |
| Coverage | **87% (5639 of 6510 statements)**; `coverage report` exit 0 against the 85% gate |
| Dependency audit | `python -m pip_audit --vulnerability-service osv --timeout 60` → **No known vulnerabilities found** after the `pypdf` pin change |
| Static checks | `ruff check .` clean; `manage.py check` clean; `makemigrations --check --dry-run` clean |
| Limitation | This is a local reproduction of the CI environment, not the remote job itself. The remote run must still be observed green after the fix is pushed — confirmed in the next entry. |

### 2026-11-19 — Remote CI confirmation (fix commit `c392370`)

The fix commit was pushed to `origin/development` and both blocking jobs were
observed to completion through the GitHub Checks API. This closes the release
blocker recorded in §10; the remote result agrees with the local PostgreSQL
reproduction above.

| Field | Value |
| --- | --- |
| Workflow run | `44538891111` — `Security checks` on `c392370` |
| `security` job | **success** (2026-11-19T13:59:05Z → 14:00:45Z) — [job](https://github.com/Davie62/nasil-supply-logistics/actions/runs/44538891111/job/135611618960) |
| `linux` job | **success** (2026-11-19T13:59:06Z → 14:01:34Z) — [job](https://github.com/Davie62/nasil-supply-logistics/actions/runs/44538891111/job/135611618356) |
| Other checks | No failing or cancelled checks on the commit |
| Result | **Release blocker cleared — both required CI jobs green** |

---

## 8. Coverage assessment

Coverage is measured with `coverage.py` against the full suite. Migrations,
virtual environments, generated output, `manage.py` and test modules are
excluded per `pyproject.toml`.

| Metric | Value |
| --- | --- |
| Statements measured | 6510 |
| Statements covered | 5632 |
| Statements missed | 878 |
| Overall statement coverage | **87% (86.5%)** |
| CI gate | `coverage report` with `fail_under = 85` in `pyproject.toml` |

The measurement is taken from the final 2026-11-19 verification run, which
reset the `.coverage` data file first (`coverage erase`). The Phase 2 baseline
was 5303 of 6109 statements; Phase 3 added 54 tests and 401 measured statements
while holding the overall figure at 87%. An earlier 2026-11-16 run did not
reset the file, so its slightly higher figure is not used.

The threshold is set two percentage points below the measured baseline (87%)
to prevent regressions without blocking unrelated feature work. It will be
raised as the remaining untested modules gain suites.

Phase 3 operational modules:

| Module | Statements | Missed | Coverage |
| --- | ---: | ---: | ---: |
| `core/backup.py` | 196 | 21 | 89% |
| `core/management/commands/backup_database.py` | 52 | 7 | 87% |
| `backend/settings.py` | 203 | 9 | 96% |

The uncovered lines in `core/backup.py` are defensive branches for unreadable
manifests, malformed headers and short reads that require crafted corruption to
reach; the command-level negative paths are covered.

### 8.1 Coverage by application (services layer)

The five Phase 2 applications are covered at the service layer, which is where
the business controls live:

| Module | Statements | Missed | Coverage |
| --- | ---: | ---: | ---: |
| `orders/services.py` | 97 | 4 | 96% |
| `inventory/services.py` | 87 | 4 | 95% |
| `procurement/services.py` | 138 | 6 | 96% |
| `fleet/services.py` | 131 | 2 | 98% |
| `finance/services.py` | 132 | 8 | 94% |

Supporting modules in the same flow also moved: `operations/services.py` 90%,
`operations/models.py` 97%, `payments/services.py` 89%,
`shipments/workflows.py` 98%, `quotations/workflows.py` 96%.

### 8.2 Coverage interpretation

- High coverage in `orders`, `inventory`, `procurement`, `fleet` and `finance`
  reflects the new service-level suites.
- Lower coverage is expected in view/template layers exercised indirectly, in
  integration adapters that require live providers, and in administrative
  modules.
- Coverage is a regression signal, not a security proof. A covered line can
  still contain a logic flaw; the negative-path assertions in §6 are the
  primary control evidence.

---

## 9. Findings and observations

No critical or high-severity product defects were identified in the Phase 2 or
Phase 3 scope. Phase 2 recorded four low/informational observations (F-01 to
F-04) and one test-reliability defect (F-05, medium, closed). Phase 3 adds one
test-validity defect (F-06, medium, closed) and two implementation defects found
and fixed before completion (F-07, F-08, low, closed). None blocks the Phase 3
objective.

### F-01 — Fleet checkpoint coordinate type handling

| Field | Value |
| --- | --- |
| Severity | Low |
| Component | `fleet/services.py` — `record_checkpoint` |
| Status | Open — backlog |
| Evidence | The service compares `latitude`/`longitude` against numeric bounds, then persists them to `DecimalField(max_digits=9, decimal_places=6)`. A JSON/form `float` is expanded to a binary decimal and fails validation ("no more than 6 decimal places"); a `str` fails the bounds comparison with `TypeError`. Only `Decimal` inputs satisfy both paths. |
| Impact | API or form callers passing floats can receive an unexpected validation error. No data corruption or authorization bypass. |
| Recommendation | Normalize coordinates at the service boundary, e.g. `Decimal(str(value))`, before validation and persistence. |
| Test disposition | The suite passes `Decimal` values and asserts the persisted scale. |

### F-02 — SQLite decimal aggregate precision in purchase totals

| Field | Value |
| --- | --- |
| Severity | Low / environment-specific |
| Component | `procurement/services.py` — `add_purchase_line` |
| Status | Open — backlog |
| Evidence | `PurchaseOrder.total` is derived from `Sum(line_total)` without quantizing. On SQLite a cents-valued total (for example `3 × 19.99`) surfaced with more than two decimal places and failed `full_clean`; PostgreSQL returns the column scale. |
| Impact | Local and Windows-CI tests using cents-valued purchase lines can fail even though production PostgreSQL is unaffected. |
| Recommendation | Quantize the aggregate to two decimals before persistence. |
| Test disposition | The Phase 2 total test uses a whole-unit total so the suite remains portable; the cents case is deferred with this finding. |

### F-03 — Test-harness note: cached employee profile

| Field | Value |
| --- | --- |
| Severity | Informational |
| Component | Test fixture only |
| Status | Closed — test implementation adjusted |
| Evidence | The `post_save` signal on `User` creates an `EmployeeProfile` and Django caches the reverse one-to-one on the user instance. Updating the profile status in the database did not affect the cached object. |
| Impact | None in production. A naive test could assert the wrong status. |
| Recommendation | Tests that mutate a profile must refresh or invalidate the reverse cache. |
| Test disposition | `fleet/tests.py` updates the profile instance and clears `user._state.fields_cache["profile"]`. |

### F-04 — Checkpoint service return value

| Field | Value |
| --- | --- |
| Severity | Informational |
| Component | `fleet/services.py` — `record_checkpoint` |
| Status | Open — backlog (API clarity) |
| Evidence | The function persists a `RouteCheckpoint` but returns the updated `Assignment`. |
| Impact | Callers expecting the created checkpoint must re-query. No functional defect. |
| Recommendation | Return the checkpoint, or document the assignment return explicitly. |
| Test disposition | The suite queries `RouteCheckpoint` directly and asserts the assignment/shipment effects. |

### F-05 — Wall-clock flakiness in the public tracking rate-limit test

| Field | Value |
| --- | --- |
| Severity | Medium (test reliability) |
| Component | `customer_services/tests.py` — `test_public_tracking_form_supports_ids_and_limits_enumeration` |
| Status | **Closed — test made deterministic** |
| Evidence | The test issued 60 allowed requests and asserted the 61st returns `429`. `allow_request` buckets by `int(now.timestamp()) // 60`, so a 60-second window boundary inside the loop reset the counter and the 61st request returned `200`. Observed on the 2026-11-18 rerun (`AssertionError: 200 != 429`); the same suite passed on 2026-11-16. |
| Impact | A false failure in the safety net. The production limiter is correct; only the test was non-deterministic. Estimated ~3% failure rate per full run, which is enough to erode trust in CI. |
| Recommendation | Freeze the clock while the burst is issued so the window cannot roll. |
| Test disposition | The burst now runs inside `patch("customer_services.security.timezone.now", return_value=frozen)`. Verified by three consecutive isolated runs (all `OK`) and the full-suite rerun in §7. |

### F-06 — Settings tests were not hermetic against a developer `.env`

| Field | Value |
| --- | --- |
| Severity | Medium (test validity) |
| Component | `backend/test_settings.py` — `DeploymentConfigurationTests.settings` |
| Status | **Closed — fixed in Phase 3** |
| Evidence | The helper cleared `os.environ` and then executed `settings.py`. `settings.py` calls `load_dotenv(BASE_DIR / ".env", override=False)`, so a developer `.env` created on 2026-11-19 refilled the environment and defeated the fail-closed assertions. Reverting the Phase 3 settings changes still produced 13 failures and 1 error on the unmodified suite. |
| Impact | The configuration safety net silently stopped proving that production fails closed whenever a `.env` existed. This is a false-negative risk in the control that protects secrets, TLS and the database engine. |
| Recommendation | Patch `dotenv.load_dotenv` while evaluating settings in tests, so only the test-supplied environment is visible. |
| Test disposition | `settings()` now wraps the evaluation in `patch.dict(..., clear=True)` **and** `patch("dotenv.load_dotenv")`. All 17 settings tests pass, including the pre-existing production checks. |

### F-07 — Empty S3 endpoint produced an invalid boto3 endpoint

| Field | Value |
| --- | --- |
| Severity | Low (implementation defect, caught before merge) |
| Component | `backend/settings.py` — `AWS_S3_ENDPOINT_URL` |
| Status | **Closed — fixed in Phase 3** |
| Evidence | The variable defaulted to `""`. Passing `endpoint_url=""` to `S3Storage` caused boto3 to raise `ValueError: Invalid endpoint: ` during storage initialisation, so the default AWS path failed even though no custom endpoint was configured. |
| Impact | Any deployment that left `AWS_S3_ENDPOINT_URL` blank would fail to initialise media storage. |
| Recommendation | Coerce an empty value to `None` and only add `endpoint_url` to the backend options when it is set. |
| Test disposition | `core/test_storage.py` and `backend/test_settings.py` exercise the default AWS path; the option is omitted when unset. |

### F-08 — Backup manifest could not serialise a `WindowsPath`

| Field | Value |
| --- | --- |
| Severity | Low (implementation defect, caught by the local drill) |
| Component | `core/management/commands/backup_database.py` — manifest payload |
| Status | **Closed — fixed in Phase 3** |
| Evidence | SQLite stores `DATABASES["default"]["NAME"]` as a `Path`. The manifest embedded it directly, so `json.dumps` raised `TypeError: Object of type WindowsPath is not JSON serializable` after the encrypted dump had already been written. |
| Impact | A backup could fail after producing an orphaned ciphertext file. The command now converts the name to `str` and removes a partial file if manifest writing fails. |
| Recommendation | Keep manifests JSON-primitive and clean up on failure. |
| Test disposition | `core/test_backup.py` asserts the manifest contents and command failure handling; the local drill in §7 produced a valid manifest. |

### F-09 — PostgreSQL restore did not refuse the live database

| Field | Value |
| --- | --- |
| Severity | High (destructive-operation guard, caught in final review before release) |
| Component | `core/backup.py` — `restore_database` |
| Status | **Closed — fixed in Phase 3** |
| Evidence | The command help promises that the live database is always refused, and the SQLite branch enforced that check. The PostgreSQL branch accepted any `--target-database`, including the live `DATABASES["default"]["NAME"]`, and would have run `pg_restore --clean --if-exists` against it. The SQLite guard also resolved the target path only when it already existed, so an absent path naming the live database could be selected. |
| Impact | An operator error or a misconfigured automation could destroy the live database during a restore drill, despite the documented guarantee. |
| Recommendation | Compare the PostgreSQL target name with the live database name, and resolve SQLite paths before the existence check; refuse on equality in both branches. |
| Test disposition | `core/test_backup.py` now asserts that PostgreSQL refuses the live name and that SQLite refuses both an existing and an absent live path; 38 backup tests pass. |

### F-10 — PostgreSQL concurrency tests leaked thread-local connections

| Field | Value |
| --- | --- |
| Severity | Medium (CI reliability; created a permanently red Linux job) |
| Component | `accounts/test_concurrency.py`, `core/test_workflow_concurrency.py`, `operations/test_concurrency.py` |
| Status | **Closed — fixed during remote CI remediation** |
| Evidence | Under portable PostgreSQL 17.10 the four assertions passed, but test-database teardown raised `psycopg.errors.ObjectInUse: database "test_nasil" is being accessed by other users` (2 sessions). `close_old_connections()` only closes invalid connections; healthy thread-local connections remained open until process exit. |
| Impact | The Linux CI job failed after a passing test run, blocking Phase 3 release. The production code was unaffected — this is a test-harness defect. |
| Recommendation | Close the connection explicitly in each worker's `finally` block so teardown can drop the test database. |
| Test disposition | All three worker helpers now call `connection.close()`; the four tests pass and the test database drops cleanly under PostgreSQL. |

### F-11 — Vulnerable `pypdf` pin in production requirements

| Field | Value |
| --- | --- |
| Severity | Medium (known CVEs in a PDF-parsing dependency) |
| Component | `requirements.txt` — `pypdf==6.21.2` |
| Status | **Closed — fixed during remote CI remediation** |
| Evidence | `pip_audit --vulnerability-service osv --timeout 60` reported 7 CVEs (CVE-2026-119203 through CVE-2026-119209) against `pypdf 6.21.2`; upstream fixed them in `6.21.4`. |
| Impact | The security job was red on every pushed commit, and PDF ingestion would ship with known parser vulnerabilities. |
| Recommendation | Raise the pin to the minimal fixed version `6.21.4`; keep the audit step as a blocking CI gate. |
| Test disposition | Pinned to `6.21.4`, installed locally, audit re-run clean; the `PdfReader` call sites in `operations/services.py`, `operations/tests.py` and `customer_services/tests.py` pass in the full PostgreSQL run. |

---

## 10. Residual risk and limitations

| Risk | Assessment | Mitigation / next step |
| --- | --- | --- |
| Docker unavailable locally | Compose supervision changes were configured and YAML-validated but not started in this environment. The PostgreSQL CI condition was independently reproduced with a portable PostgreSQL 17.10 cluster. | Observe the first remote CI run; treat a red run as a release blocker. Run `docker compose up` on a Docker-capable host before the pilot. |
| PostgreSQL-specific behaviour | Resolved for this release: the full suite now runs locally on PostgreSQL 17.10 (327 tests, 327 passed, 0 skipped) as well as on SQLite. | Keep the Linux CI job on PostgreSQL 17 so future regressions are caught. |
| PostgreSQL restore drill | The local drill restored SQLite byte-for-byte. `pg_dump`/`pg_restore` argument construction is unit-tested with mocks, but no real PostgreSQL restore was executed. | Run `backup_database` then `restore_database --target-database <isolated>` on staging and compare counts. |
| Live S3 bucket | Storage tests use the `moto` mock. Bucket policy, IAM role, lifecycle rules and presigned URL expiry against real AWS were not exercised. | Apply the documented bucket policy, verify an upload/presign/read cycle, and confirm public access is blocked at the account level. |
| Systemd supervision | Unit and timer files are reviewed but not started; no host ran them. | Install on staging, confirm `systemctl list-timers`, kill the worker and beat to verify restart, and confirm beat does not replay overdue tasks. |
| Live provider integrations | Not exercised. | Sandbox acceptance with SendGrid, Twilio, Africa's Talking, Odoo, Flutterwave and pawaPay remains outstanding. |
| Browser and accessibility acceptance | Not exercised. | Add repeatable browser CI and a manual accessibility pass before release. |
| Performance and load | Not exercised. | Run realistic concurrency/load tests during the operational pilot. |
| Coverage threshold calibration | Threshold is conservative and based on one full run per phase. | Re-measure after each phase and ratchet upward. |
| Findings F-01, F-02, F-04 | Low/informational; no production data impact. | Schedule in the next maintenance pass; add regression tests with the fixes. |

---

## 11. Change log

| Date | Version | Change | Author |
| --- | --- | --- | --- |
| 2026-11-19 | 1.6 | Corrected a factual error in document control: test framework was recorded as Django 6.0; installed and pinned version is 6.1.2 (documentation only) | QA / security review |
| 2026-11-19 | 1.5 | Remote CI confirmation recorded: workflow run `44538891111` — `security` and `linux` jobs both success on `c392370`; release blocker cleared (documentation only) | QA / security review |
| 2026-11-19 | 1.4 | Remote CI remediation: F-10 (thread-local connection leak blocked PostgreSQL test-DB teardown) and F-11 (`pypdf` CVEs) closed; full suite green on PostgreSQL 17.10 (327 passed, 0 skipped), 87% (5639/6510), `pip_audit` clean, static checks clean | QA / security review |
| 2026-11-19 | 1.3 | Final verification after F-09: live-database refusal added to PostgreSQL/SQLite restore; 63 focused tests, 327 full tests (323 passed, 4 skipped), 87% (5632/6510); static checks clean | QA / security review |
| 2026-11-19 | 1.2 | Phase 3 recorded: durable private S3 media, worker/beat supervision, encrypted backup/restore, operational health probe; 61 focused tests; full regression 325 tests, 321 passed, 4 skipped, 0 failed; 87% (5637/6508); byte-identical local restore drill; findings F-06–F-08 raised and closed | QA / security review |
| 2026-11-18 | 1.1 | Rerun recorded: 273 tests, 269 passed, 4 skipped, 0 failed; clean coverage baseline 87% (5303/6109); F-05 raised and closed by freezing the clock in the public tracking rate-limit test; coverage gate set to `fail_under = 85` | QA / security review |
| 2026-11-16 | 1.0 | Initial Phase 2 record: five new suites (53 tests), full regression, coverage gate, CI PostgreSQL/Redis services, findings F-01–F-04 | QA / security review |
| 2026-11-16 | 1.0 | Phase 1 baseline recorded: 220 tests, 4 PostgreSQL-only skipped, static checks clean | QA / security review |

### 11.1 Phase 2 change set

| File | Change |
| --- | --- |
| `core/test_commercial_fixtures.py` | New shared commercial fixture mixin and permission set |
| `orders/tests.py` | New 10-test order lifecycle suite |
| `inventory/tests.py` | New 9-test inventory suite |
| `procurement/tests.py` | New 11-test procurement suite |
| `fleet/tests.py` | New 11-test fleet suite |
| `finance/tests.py` | New 12-test finance suite |
| `.github/workflows/security.yml` | PostgreSQL 17 + Redis 7 services, development dependencies, ruff, coverage gate |
| `pyproject.toml` | `fail_under = 85` coverage regression gate |
| `customer_services/tests.py` | F-05 fix: freeze the clock during the public tracking rate-limit burst |
| `TEST_AUDIT_LOG.md` | This document |

### 11.2 Phase 3 change set

| File | Change |
| --- | --- |
| `backend/settings.py` | `STORAGES` selection, private S3 backend options, `MEDIA_STORAGE_ALLOW_EPHEMERAL`, `BACKUP_*` settings and validation |
| `backend/test_settings.py` | Hermetic settings evaluation; media, backup and presign tests |
| `backend/test_celery.py` | Beat schedule integrity tests |
| `core/backup.py` | Chunked Fernet encryption, manifests, checksums, retention, `pg_dump`/`pg_restore` helpers, live-target refusal (F-09) |
| `core/management/commands/backup_database.py` | Encrypted backup command with pruning and cleanup on failure |
| `core/management/commands/restore_database.py` | Confirmation-gated restore into an isolated target |
| `core/management/commands/check_operational_health.py` | Database, migration, broker, storage and backup-age probe |
| `core/test_backup.py` | 38 tests across encryption, manifests, retention, commands, restore safety and health checks |
| `core/test_storage.py` | 5 `moto`-backed private-media tests |
| `deploy/systemd/` | Web, worker, beat, backup and health units plus timers |
| `docker-compose.yml` | Restart policies, worker/beat healthchecks, beat schedule persistence |
| `requirements.txt` | `boto3`, `django-storages[s3]` |
| `requirements-development.txt` | `moto[s3]` |
| `.env.example`, `DEPLOYMENT.md` | Media, backup, restore-drill, monitoring and supervision documentation |
| `TEST_AUDIT_LOG.md` | This document |

### 11.3 Remote CI remediation change set

| File | Change |
| --- | --- |
| `accounts/test_concurrency.py` | F-10: worker threads close their DB connection explicitly instead of relying on `close_old_connections()` |
| `core/test_workflow_concurrency.py` | F-10: same connection-close fix in the workflow race helper |
| `operations/test_concurrency.py` | F-10: same connection-close fix in the inventory race helper |
| `requirements.txt` | F-11: `pypdf` pinned from `6.21.2` to `6.21.4` (7 CVEs fixed) |
| `TEST_AUDIT_LOG.md` | This document |

---

## 12. Sign-off

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| QA / security review | AI-assisted review | Remote CI remediation verified locally and remotely: F-10/F-11 closed, full suite green on PostgreSQL 17.10 (327/327), `pip_audit` clean, workflow run `44538891111` both jobs success | 2026-11-19 |
| QA / security review | AI-assisted review | Phase 3 final verification passed; F-05–F-09 closed before release, F-01/F-02/F-04 remain low/informational backlog; no open critical/high findings | 2026-11-19 |
| QA / security review | AI-assisted review | Phase 3 objective met; no critical/high findings | 2026-11-19 |
| QA / security review | AI-assisted review | Phase 2 test objective met; no critical/high findings | 2026-11-16 |
| Engineering lead | — | **Pending review** | — |
| Product owner | — | **Pending acceptance** | — |

**Statement of limitations.** This record evidences the tests that were run and
their results. It does not certify production readiness, live integration
correctness, regulatory compliance, or freedom from vulnerabilities. Those
require the separate acceptance activities listed in §10.
