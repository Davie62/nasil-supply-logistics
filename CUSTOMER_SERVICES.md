# Customer services

Implemented locally on 27 October 2026. The portal uses Django authentication,
ORM QuerySets, shared template blocks and the NASIL Bootstrap 5 visual style.
The requested `portal-builder`, `tracking-service` and `notification-engine`
skills were unavailable; the implementation is in the project itself.

## Screens and access

- `/portal/login/`: customer login, lockout and password recovery.
- `/portal/register/`: customers choose their own username/password and contact details.
- `/portal/verify-email/`: six-digit email verification, without activation URLs.
- `/portal/`: customer dashboard, quotations, shipments, invoices and notifications.
- `/portal/preferences/`: email or consented SMS, notification categories and opt-out.
- `/track/`: anonymous tracking ID lookup with status, timeline and delivery-proof
  confirmation. Signed files, recipient names, addresses, cargo, internal notes and
  staff identities remain private. Tracking is limited to 60 requests/minute per IP.
- `/customer-services/customers/<id>/access/`: authorized staff invite customers,
  replace pending invitations or enable/disable access. Linked from Customers.
- `/customer-services/invoices/`: Finance/Admin issue, view, void and export invoices.

Customers can register directly from **Create account** on the customer login page.
Email verification uses a ten-minute, six-digit code; five wrong attempts invalidate
the code, with throttled resend and a one-minute cooldown. Until verification, the
account has no CustomerAccess and cannot access quotations, shipments or documents.
Existing customer records are linked only after verification; registration never
overwrites their contact details. Existing staff/login identities are not claimed.
Unfinished registration can resume through customer login. Email owners can recover
an unfinished account through password reset; the recovery email includes the
username and does not grant portal access before verification. Codes are hashed for
verification; the delivery outbox temporarily holds the email code and removes it
after provider acceptance, completion or replacement. Verification events are audited.

When DEBUG is true and notification delivery is disabled, only the registration
session sees a clearly labelled local code preview. The preview never appears in
production. Production registration requires enabled SendGrid delivery and sender
configuration; existing Celery workers and beat deliver the code. Establish cleanup
and retention for abandoned unverified accounts before public deployment.

Optional staff invitations remain available: staff issue a seven-day, single-use invitation to the recorded customer email.
Activation creates a nonstaff account linked to exactly one customer. Existing
accounts are never claimed by matching an email address. Changing the recorded
email invalidates outstanding invitations and stops external delivery until the
verified identity is reconciled by an administrator. Disabling access takes effect
on subsequent portal requests and notification delivery checks.

Customer views scope every detail, download and QuerySet to the authenticated
CustomerAccess relationship. Staff cannot sign into the customer portal. Search
and pagination execute on QuerySets with 25 rows per page. Public tracking receives
a whitelist projection rather than the shipment model or raw audit differences.
New tracking IDs use full UUID entropy; existing IDs remain valid.

## Models and reusable examples

`customer_services/models.py` defines CustomerAccess, PortalInvitation,
NotificationPreference, CustomerNotification, DeliveryAttempt and RateBucket.
Invoices use `payments.models.Invoice`; proofs reuse operations.DeliveryProof.
Invoices preserve customer and pricing snapshots, lock quotation repricing and
reassignment, and retain void history. They do not record settlement or payments.

The actual views follow this ownership pattern:

```python
@customer_required
@require_GET
def shipment_detail(request, pk):
    shipment = get_object_or_404(
        Shipment.objects.select_related("quote").filter(
            quote__customer=request.customer), pk=pk)
    return render(request, "portal/shipment.html", {"shipment": shipment})
```

Use existing portal components rather than repeating page structure:

```django
{% extends "portal/base.html" %}
{% block content %}
  {% include "portal/components/heading.html" %}
  {% include "portal/components/shipment_table.html" %}
  {% include "operations/components/pagination.html" %}
{% endblock %}
```

Business services remain the write entry points:

```python
invitation = invite_customer(actor=staff, customer_id=customer.pk)
access = activate_customer(token=invitation_token(invitation),
                          username=username, password=password)
invoice = issue_invoice(actor=finance, quote_id=approved_quote.pk,
                        due_date=due_date, customer_note="Thank you")
```

## Notification delivery

AuditRecord signals enqueue quotation approvals, shipment booking/status updates,
location/ETA changes, delivery confirmations and proof availability. Invoice creation
also queues a notification. Per-event unique keys prevent duplicate outbox rows;
database rollback removes the corresponding queued event. No historical backfill is
sent. `templates/notifications/` provides email text/HTML and SMS templates with
dynamic placeholders and a canonical portal link. Password recovery always uses
the verified email address, even when transactional SMS is preferred or opted out.

SendGrid is the email provider. SMS starts with Twilio and uses Africa's Talking
when a fallback-eligible failure occurs. Invalid recipients/payloads are terminal;
temporary failures retry with exponential delays, up to five claimed attempts.
Configuration/authentication failures are visible and require operator intervention.
The durable outbox retains queued events if Redis is unavailable; Celery beat
republishes due work every minute. Workers claim rows with expiring leases and
recheck current ownership, preferences and recipients before delivery.

Delivery is **at least once**. A timeout or worker crash after provider acceptance
can cause a duplicate, including when switching SMS providers. `sent` means provider
accepted, not handset/inbox delivered. Delivery-receipt webhooks are a future
extension. Business operations are never replayed by notification retries.

## Environment and workers

Use `.env.example` as an inventory; Django does not load it automatically. Supply
secrets through the hosting environment. Required settings include:

```text
PUBLIC_SITE_URL=https://your-nasil-domain.example
CELERY_BROKER_URL=redis://redis-host:6379/0
SENDGRID_API_KEY=...
DEFAULT_FROM_EMAIL=verified-sender@your-domain.example
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=...
AFRICASTALKING_USERNAME=...
AFRICASTALKING_API_KEY=...
AFRICASTALKING_SENDER_ID=...
NOTIFICATIONS_DELIVERY_ENABLED=false
```

Twilio can use TWILIO_MESSAGING_SERVICE_SID instead of TWILIO_FROM_NUMBER.
AFRICASTALKING_SANDBOX defaults to false. Validate sender registration, credentials,
canonical HTTPS links and test recipients in staging before enabling delivery.
Run Redis separately, with protected network access and appropriate persistence.

```bash
celery -A backend worker --loglevel=INFO
celery -A backend beat --loglevel=INFO
```

Use supervised Linux workers for deployment. Windows development can use
`celery -A backend worker --pool=solo --loglevel=INFO` for manual checks; Windows
is not a supported Celery production worker platform. Run one beat scheduler.

Operational commands:

```bash
python manage.py dispatch_customer_notifications          # count only
python manage.py dispatch_customer_notifications --publish
python manage.py retry_customer_notification UUID         # failed/exhausted only
python manage.py cleanup_tracking_limits
```

Schedule rate-bucket cleanup daily. Authorized Django admin users can inspect
read-only outbox and provider attempts; credentials/provider response bodies are
not logged. Establish retention for notification recipients, recovery payloads,
audit records and private delivery evidence before production.

## Verification and remaining launch work

The full local suite ran 146 tests: 142 passed, four PostgreSQL-only tests skipped.
Coverage includes cross-customer denial, private proof downloads, redacted tracking,
invitation replay/expiry, password recovery, preferences, invoice snapshots,
transaction rollback, deduplication, provider contracts, retry limits and fallback.
Provider calls are mocked; no real customer messages were sent.
After browser verification corrected the form referrer policy, all 36 customer
service tests passed again. Chrome checks covered login, preference saving, logout,
public tracking submission and layouts at 1440, 768 and 390 pixels. The sample
invoice PDF was rendered and visually inspected. Migrations were applied to the
local database after a verified backup; all existing data in 23 tables was preserved.

Self-registration validation: the full suite passed 154 tests with four PostgreSQL
checks skipped. After adding recovery for unfinished accounts, all 49 customer-service
tests passed. The browser signup/verification flow completed, and mobile registration
and code-entry screens were visually inspected. The registration migration preserved
existing data across 30 tables after a verified database backup.

Configure actual credentials, deploy Redis/workers/beat, test provider sandbox/live
test recipients and PostgreSQL concurrency in staging. Complete the DEPLOYMENT.md
launch checks before external access. Payments, tax-compliant invoice numbering,
customer acceptance, delivery receipts and staff MFA remain
separate requirements.

Provider references: [Celery Django integration](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html),
[SendGrid Mail Send](https://www.twilio.com/docs/sendgrid/api-reference/mail-send/mail-send),
[Twilio Messages](https://www.twilio.com/docs/messaging/api/message-resource),
[Africa's Talking SMS SDK](https://github.com/AfricasTalkingLtd/africastalking-python/blob/master/africastalking/SMS.py).
