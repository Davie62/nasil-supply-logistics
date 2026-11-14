import ipaddress
from django.conf import settings
from django.utils.crypto import salted_hmac


def client_ip(request):
    peer = request.META.get("REMOTE_ADDR", "")
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return "unknown"
    if any(address in ipaddress.ip_network(network) for network in settings.SECURITY_TRUSTED_PROXY_NETWORKS):
        # Edge must OVERWRITE X-Real-IP. Never trust arbitrary forwarded chains.
        try:
            return str(ipaddress.ip_address(request.META.get("HTTP_X_REAL_IP", peer)))
        except ValueError:
            return str(address)
    return str(address)


def ip_fingerprint(request):
    return salted_hmac("nasil-security-ip", client_ip(request)).hexdigest()
