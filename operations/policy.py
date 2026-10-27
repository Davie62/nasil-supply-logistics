from django.conf import settings


def business_policy():
    from .models import BusinessSettings
    return BusinessSettings.objects.filter(pk=1).first()


def currency_for_scope(trade_type):
    policy = business_policy()
    mapping = {"local": policy.local_currency if policy else "UGX", "international": policy.international_currency if policy else "USD"}
    return mapping.get(trade_type, "")


def threshold_policy():
    policy = business_policy()
    if policy:
        return {"UGX": policy.ugx_approval_threshold, "USD": policy.usd_approval_threshold}
    return settings.QUOTATION_APPROVAL_THRESHOLDS
