"""Small provider adapters with bounded HTTP calls and redacted errors."""
import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.conf import settings


class ProviderError(Exception):
    def __init__(self, code, retryable=True, fallback=True):
        self.code, self.retryable, self.fallback = code, retryable, fallback
        super().__init__(code)


def request_provider(url, data, headers):
    try:
        request = Request(url, data=data, headers=headers, method="POST")
        with urlopen(request, timeout=10) as response:
            raw = response.read(1024 * 1024)
            return response.status, response.headers, json.loads(raw) if raw else {}
    except HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        raise ProviderError(f"http_{error.code}", retryable=retryable, fallback=retryable or error.code in {401, 403}) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("network_unavailable") from None
    except (ValueError, TypeError):
        # A malformed/uncertain provider response must not trigger immediate failover:
        # the provider may already have accepted the message.
        raise ProviderError("invalid_provider_response", fallback=False) from None


def sendgrid(notification, text, html):
    if not settings.SENDGRID_API_KEY or not settings.DEFAULT_FROM_EMAIL:
        raise ProviderError("sendgrid_not_configured", retryable=False)
    payload = {"personalizations": [{"to": [{"email": notification.recipient}], "custom_args": {"notification_id": str(notification.reference)}}],
               "from": {"email": settings.DEFAULT_FROM_EMAIL}, "subject": notification.title,
               "content": [{"type": "text/plain", "value": text}, {"type": "text/html", "value": html}]}
    status, headers, data = request_provider("https://api.sendgrid.com/v3/mail/send", json.dumps(payload).encode(),
        {"Authorization": "Bearer " + settings.SENDGRID_API_KEY, "Content-Type": "application/json"})
    if status != 202:
        raise ProviderError("sendgrid_not_accepted")
    return headers.get("X-Message-Id", "")[:255]


def twilio(notification, sms):
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", settings.TWILIO_ACCOUNT_SID) or not settings.TWILIO_AUTH_TOKEN or not (settings.TWILIO_FROM_NUMBER or settings.TWILIO_MESSAGING_SERVICE_SID):
        raise ProviderError("twilio_not_configured", retryable=False)
    fields = {"To": notification.recipient, "Body": sms}
    fields["MessagingServiceSid" if settings.TWILIO_MESSAGING_SERVICE_SID else "From"] = settings.TWILIO_MESSAGING_SERVICE_SID or settings.TWILIO_FROM_NUMBER
    auth = base64.b64encode(f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()).decode()
    status, headers, data = request_provider(f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json", urlencode(fields).encode(),
        {"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"})
    if status != 201 or not data.get("sid"):
        raise ProviderError("twilio_not_accepted", fallback=False)
    return str(data["sid"])[:255]


def africastalking(notification, sms):
    if not settings.AFRICASTALKING_USERNAME or not settings.AFRICASTALKING_API_KEY:
        raise ProviderError("africastalking_not_configured", retryable=False)
    host = "api.sandbox.africastalking.com" if settings.AFRICASTALKING_SANDBOX else "api.africastalking.com"
    fields = {"username": settings.AFRICASTALKING_USERNAME, "to": notification.recipient, "message": sms, "bulkSMSMode": 1}
    if settings.AFRICASTALKING_SENDER_ID:
        fields["from"] = settings.AFRICASTALKING_SENDER_ID
    status, headers, data = request_provider(f"https://{host}/version1/messaging", urlencode(fields).encode(),
        {"apiKey": settings.AFRICASTALKING_API_KEY, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    recipients = data.get("SMSMessageData", {}).get("Recipients", [])
    if not recipients or recipients[0].get("statusCode") != 101:
        raise ProviderError("africastalking_not_accepted", retryable=False)
    return str(recipients[0].get("messageId", ""))[:255]
