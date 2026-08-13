import re

from django.core.exceptions import ValidationError


def validate_phone_number(value):
    """
    Validates international phone numbers.
    Example:
        +256700123456
        0700123456
    """

    pattern = r"^(\+?[1-9]\d{7,14}|0\d{9})$"

    if not re.match(pattern, value):
        raise ValidationError(
            "Enter a valid phone number."
        )


def validate_employee_id(value):
    """
    Expected format:

    NSL-2026-00001
    """

    pattern = r"^NSL-\d{4}-\d{5}$"

    if not re.match(pattern, value):
        raise ValidationError(
            "Invalid employee ID format."
        )


def validate_company_code(value):

    if len(value) < 2:
        raise ValidationError(
            "Code must contain at least two characters."
        )

    if " " in value:
        raise ValidationError(
            "Codes cannot contain spaces."
        )