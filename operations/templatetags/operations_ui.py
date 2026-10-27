from django import template
from datetime import date, datetime
from django.utils import timezone

register = template.Library()


@register.filter
def display_value(value):
    if value is None:
        return "Not recorded"
    if isinstance(value, datetime):
        localized = timezone.localtime(value) if timezone.is_aware(value) else value
        return localized.strftime("%d %b %Y, %H:%M:%S %Z").strip()
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return value


@register.simple_tag(takes_context=True)
def querystring(context, **changes):
    query = context["request"].GET.copy()
    for key, value in changes.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()
