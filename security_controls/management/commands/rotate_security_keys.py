from django.core.management.base import BaseCommand
from django.db import transaction
from security_controls.models import MFAProfile
from security_controls.crypto import rotate_secret
from security_controls.events import security_event


class Command(BaseCommand):
    help = "Re-encrypt MFA secrets with the first SECURITY_ENCRYPTION_KEYS entry. Retain old keys until sessions expire."

    @transaction.atomic
    def handle(self, *args, **options):
        count = 0
        for profile in MFAProfile.objects.select_for_update().exclude(encrypted_secret=""):
            profile.encrypted_secret = rotate_secret(profile.encrypted_secret)
            profile.save(update_fields=["encrypted_secret", "updated_at"])
            count += 1
        security_event("encryption_keys_rotated")
        self.stdout.write(f"Rotated {count} encrypted MFA records. No secrets were displayed.")
