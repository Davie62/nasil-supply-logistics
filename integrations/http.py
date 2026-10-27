"""Bounded HTTPS JSON transport. Credentials and response bodies never enter logs."""
import ipaddress
import json
import os
import socket
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from django.conf import settings


class IntegrationError(Exception):
    def __init__(self, code, retryable=False):
        self.code, self.retryable = code, retryable
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise IntegrationError("redirect_rejected")


def token(environment_name):
    value = os.environ.get(environment_name, "")
    if not value or "\r" in value or "\n" in value:
        raise IntegrationError("credentials_not_configured")
    return value


def safe_url(url):
    parsed = urlsplit(url)
    hosts = set(settings.INTEGRATIONS_ALLOWED_HOSTS)
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.fragment or parsed.port not in {None, 443}:
        raise IntegrationError("endpoint_not_allowed")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise IntegrationError("nonpublic_endpoint_rejected")
    except socket.gaierror:
        raise IntegrationError("dns_unavailable", retryable=True) from None
    return url


def request_json(url, *, method="POST", payload=None, headers=None):
    if not settings.INTEGRATIONS_DELIVERY_ENABLED:
        raise IntegrationError("integration_delivery_disabled")
    safe_url(url)
    body = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "NASIL/1.0", **(headers or {})})
    try:
        with build_opener(HTTPSHandler(), NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise IntegrationError("provider_response_too_large")
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        raise IntegrationError(f"provider_http_{error.code}", retryable=error.code == 429 or error.code >= 500) from None
    except (URLError, TimeoutError, OSError):
        # GET is safe to retry. Uncertain financial POSTs require operator review.
        raise IntegrationError("provider_network_error", retryable=method == "GET") from None
    except (ValueError, TypeError):
        raise IntegrationError("invalid_provider_response") from None
