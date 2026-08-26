---
name: django-security-audit
description: "Use when auditing a Django project or its apps for implemented security controls, documented-only controls, security gaps, and prioritized remediation recommendations. Trigger for requests to analyze app security, authentication, authorization, CSRF, sessions, uploads, secrets, or security testing."
---

# Django Security Audit

Produce a fact-grounded security inventory for the whole Django project. The output must separate controls verified in executable code from controls mentioned only in documentation and controls that are absent.

## Workflow

1. Establish scope.
   - Identify the Django settings module, root URL configuration, installed apps, middleware, templates, static files, migrations, management commands, dependencies, and security documentation.
   - Include every local app listed in `INSTALLED_APPS`, even if it appears to be a placeholder.
   - Check repository artifacts such as seed scripts, local databases, uploaded media, environment files, and ignore rules.

2. Inspect global controls first.
   - Review `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, database configuration, HTTPS and HSTS settings, cookie flags, security middleware, CSRF middleware, clickjacking protection, content type sniffing, referrer policy, and CSP.
   - Check password validators, custom user configuration, authentication backends, session expiry, login/logout redirects, and email/password lifecycle settings.
   - Search for raw SQL, unsafe template output (`safe`, `mark_safe`), file upload handling, subprocesses, deserialization, redirects, and external requests.

3. Audit each app locally.
   - Read models for ownership or tenant boundaries, sensitive fields, validators, uniqueness and check constraints, indexes, upload fields, deletion behavior, and audit metadata.
   - Read views, forms, serializers, services, signals, admin classes, URLs, and management commands for authentication, authorization, object-level access checks, state-changing HTTP methods, validation, transactions, and logging.
   - Read tests and record whether security behavior is actually covered.
   - For each app, report one of: implemented controls, partial controls, documented-only controls, absent controls, and relevant evidence paths.

4. Verify claims instead of trusting documentation.
   - Treat a policy or roadmap statement as a requirement or planned feature unless corresponding executable code and a test are present.
   - Distinguish a field that exists from behavior that uses it. For example, lockout fields do not prove lockout enforcement.
   - Distinguish authentication from authorization: `login_required` proves login gating only, not role, branch, tenant, ownership, or object permission enforcement.
   - Distinguish database integrity from application authorization: UUIDs, soft deletion, `PROTECT`, and uniqueness constraints do not prevent unauthorized reads or writes.

5. Run cheap discriminating checks where available.
   - Run Django system checks and migrations checks.
   - Inspect URL patterns for unprotected state-changing endpoints.
   - Search for permission decorators, `has_perm`, group checks, ownership filters, CSRF tokens, raw SQL, unsafe HTML, and security settings.
   - Check whether tests contain real test methods and whether security-sensitive paths have regression coverage.
   - Do not modify application code during an audit unless the user explicitly asks for remediation.

6. Prioritize recommendations.
   - Classify findings as critical/high, medium, or low/maintenance using exposure, exploitability, affected data, and production impact.
   - Start with secret exposure, debug mode, authentication bypass, authorization bypass, credential abuse, transport security, and sensitive-data leakage.
   - For each recommendation state the control to add, the owning file/app boundary, and the validation or test that should prove it.
   - Include operational actions such as secret rotation, database/media handling, deployment configuration, monitoring, and documentation correction.

## Required Output

Return these sections in order:

1. **Scope and method**: settings, apps, artifacts, and checks examined.
2. **Global implemented controls**: only controls supported by code/config evidence.
3. **App-by-app inventory**: one subsection per local app, including explicit "none found" where applicable.
4. **Documented but unverified controls**: policy or roadmap claims without live implementation evidence.
5. **Security gaps and recommendations**: prioritized, actionable findings with evidence paths.
6. **Security test plan**: focused tests for authentication, CSRF, sessions, authorization, tenancy/ownership, lockout, uploads, admin access, validation, and production settings.
7. **Assumptions and residual risk**: limits such as runtime infrastructure, reverse-proxy configuration, secrets outside the repository, or unexecuted integration tests.

Use file links when the environment supports them. Never label a future enhancement as implemented. For each positive finding, name the mechanism and where it is configured or enforced. For each negative finding, state the search or code path that supports the conclusion.

## Completion Criteria

The audit is complete only when:

- Every installed local app has an explicit status.
- Global settings, middleware, URLs, templates, models, admin, services, commands, and tests have been considered.
- Implemented, partial, documented-only, and absent controls are separated.
- High-impact findings include remediation and a proving test or operational check.
- The report calls out dangerous development defaults and exposed repository artifacts.
- No conclusion relies solely on a security policy, README, roadmap, model field, or unused constant.
