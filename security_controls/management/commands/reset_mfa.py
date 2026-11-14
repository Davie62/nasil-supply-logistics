from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from security_controls.models import MFAProfile
from security_controls.events import security_event


class Command(BaseCommand):
    help = "Operator-only recovery: invalidate MFA after independently verifying account ownership."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--reason", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not 10 <= len(options["reason"].strip()) <= 255:
            raise CommandError("Record a recovery reason of 10–255 characters in your protected operator log.")
        user = get_user_model().objects.select_for_update().filter(username=options["username"]).first()
        if not user:
            raise CommandError("Account not found.")
        profile, _ = MFAProfile.objects.select_for_update().get_or_create(user=user)
        profile.enabled, profile.encrypted_secret, profile.recovery_hashes = False, "", []
        profile.last_counter, profile.failed_attempts, profile.locked_until = -1, 0, None
        profile.session_version += 1
        profile.revocation_version += 1
        profile.save()
        security_event("mfa_operator_reset", target_id=user.pk, level="warning")
        self.stdout.write("MFA credentials invalidated. The user must enroll again when staff MFA is required.")
