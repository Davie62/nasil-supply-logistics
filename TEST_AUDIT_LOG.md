# NASIL Supply & Logistics — Test and Security Assurance Log

## Document control

| Field | Value |
| --- | --- |
| Document ID | NASIL-TST-2026-11-16 |
| Title | Test Execution and Security Assurance Log |
| Version | 1.1 |
| Status | Phase 2 complete; awaiting engineering sign-off |
| Date of record | 2026-11-16 (initial), 2026-11-18 (rerun) |
| Classification | Internal — Engineering |
| Repository | `Davie62/nasil-supply-logistics` |
| Branch | `development` |
| Baseline commit | `1424dc7` (Phase 1) plus the Phase 2 change set recorded in §11 |
| Application | NASIL supply, logistics, commercial and finance monolith |
| Test framework | Django 6.0 test runner (`manage.py test`) |
| Assurance tooling | `coverage.py` 7.17.3, `ruff` 0.17.5, Django system checks, migration drift check |
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
the architecture findings in `PROJECT_STATUS_REVIEW.md`, in particular the P2
automation gap: *"PostgreSQL/browser CI coverage is incomplete."*

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
- Infrastructure, backup/restore, monitoring and incident-response testing.
- Formal penetration testing or third-party security assessment.

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

Counts are test methods. "Result" reflects the 2026-11-16 full run.

| Suite | File | Tests | Primary controls | Result |
| --- | --- | ---: | --- | --- |
| Accounts (incl. concurrency) | `accounts/tests.py`, `accounts/test_concurrency.py` | 12 | Authentication, lockout, MFA, employee lifecycle, PostgreSQL row locks | Pass / 1 skipped on SQLite |
| Backend configuration | `backend/test_settings.py` | 9 | Fail-closed settings, TLS, PostgreSQL requirement | Pass |
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
| **Total** | | **273** | | **269 passed, 4 skipped, 0 failed** |

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

---

## 8. Coverage assessment

Coverage is measured with `coverage.py` against the full suite. Migrations,
virtual environments, generated output, `manage.py` and test modules are
excluded per `pyproject.toml`.

| Metric | Value |
| --- | --- |
| Statements measured | 6109 |
| Statements covered | 5303 |
| Statements missed | 806 |
| Overall statement coverage | **87% (86.8%)** |
| CI gate | `coverage report` with `fail_under = 85` in `pyproject.toml` |

The measurement is taken from the 2026-11-18 run, which reset the `.coverage`
data file first (`coverage erase`). An earlier 2026-11-16 run did not reset the
file, so its slightly higher figure is not used.

The threshold is set two percentage points below the measured baseline (87%)
to prevent regressions without blocking unrelated feature work. It will be
raised as the remaining untested modules gain suites.

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

No critical or high-severity product defects were identified in the Phase 2
scope. Four low/informational observations (F-01 to F-04) and one
test-reliability defect (F-05, medium, closed) were recorded. None blocks the
Phase 2 objective.

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

---

## 10. Residual risk and limitations

| Risk | Assessment | Mitigation / next step |
| --- | --- | --- |
| Docker unavailable locally | The PostgreSQL/Redis CI job was configured and YAML-validated but not executed in this environment. | Observe the first remote CI run on the Phase 2 push; treat a red run as a release blocker. |
| PostgreSQL-specific behaviour | Local runs use SQLite; four concurrency checks are skipped. | The Linux CI job runs the full suite on PostgreSQL 17. |
| Live provider integrations | Not exercised. | Sandbox acceptance with SendGrid, Twilio, Africa's Talking, Odoo, Flutterwave and pawaPay remains outstanding. |
| Browser and accessibility acceptance | Not exercised. | Add repeatable browser CI and a manual accessibility pass before release. |
| Performance and load | Not exercised. | Run realistic concurrency/load tests during the operational pilot. |
| Coverage threshold calibration | Threshold is conservative and based on one full run. | Re-measure after each phase and ratchet upward. |
| Findings F-01, F-02, F-04 | Low/informational; no production data impact. | Schedule in the next maintenance pass; add regression tests with the fixes. |

---

## 11. Change log

| Date | Version | Change | Author |
| --- | --- | --- | --- |
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

---

## 12. Sign-off

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| QA / security review | AI-assisted review | Phase 2 test objective met; no critical/high findings | 2026-11-16 |
| Engineering lead | — | **Pending review** | — |
| Product owner | — | **Pending acceptance** | — |

**Statement of limitations.** This record evidences the tests that were run and
their results. It does not certify production readiness, live integration
correctness, regulatory compliance, or freedom from vulnerabilities. Those
require the separate acceptance activities listed in §10.
