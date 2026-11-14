"""Validate structure and bounds; ORM parameters and template escaping handle context."""
import json
import re
import math
from django.core.exceptions import ValidationError

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value, *, limit=4096, multiline=True):
    if not isinstance(value, str) or len(value) > limit or CONTROL.search(value) or (not multiline and ("\r" in value or "\n" in value)):
        raise ValidationError("Text contains invalid characters or exceeds the permitted length.")
    return value


def positive_integer(value, maximum=1000000):
    if not re.fullmatch(r"[1-9][0-9]{0,9}", value) or int(value) > maximum:
        raise ValidationError("Choose a valid positive integer.")
    return int(value)


def strict_json(body, *, allowed_fields=None, required_fields=()):
    if len(body) > 65536:
        raise ValidationError("JSON payload is too large.")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result or key in {"__proto__", "constructor", "prototype"}:
                raise ValueError()
            clean_text(key, limit=100, multiline=False)
            result[key] = value
        return result

    def inspect(value, depth=0):
        if depth > 10:
            raise ValueError()
        if isinstance(value, str):
            clean_text(value, limit=16000)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError()
        elif isinstance(value, dict):
            for item in value.values():
                inspect(item, depth+1)
        elif isinstance(value, list):
            if len(value) > 1000:
                raise ValueError()
            for item in value:
                inspect(item, depth+1)

    try:
        value = json.loads(body, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict) or (allowed_fields is not None and set(value)-set(allowed_fields)) or not set(required_fields) <= set(value):
            raise ValueError()
        inspect(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValidationError("Submit a valid JSON object with supported fields and no duplicate keys.") from None
