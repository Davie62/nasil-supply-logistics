"""Authenticated encryption with a separate, rotatable environment key ring."""
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.views.decorators.debug import sensitive_variables


def cipher():
    try:
        return MultiFernet([Fernet(key.encode()) for key in settings.SECURITY_ENCRYPTION_KEYS])
    except (ValueError, TypeError):
        raise ImproperlyConfigured("Configure SECURITY_ENCRYPTION_KEYS with valid Fernet keys.") from None


@sensitive_variables()
def encrypt_secret(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt_secret(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError, ValueError):
        raise ValidationError("The protected value cannot be decrypted. Contact your administrator.") from None


def rotate_secret(value):
    try:
        return cipher().rotate(value.encode()).decode()
    except InvalidToken:
        raise ValidationError("The protected value cannot be rotated.") from None
