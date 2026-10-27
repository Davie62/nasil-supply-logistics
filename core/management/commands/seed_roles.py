from django.core.management.base import BaseCommand
from accounts.roles import seed_role_permissions


class Command(BaseCommand):
    help = "Add default role permissions without creating organization or user records."

    def handle(self, *args, **options):
        seed_role_permissions()
        self.stdout.write(self.style.SUCCESS("Role permissions ready; user memberships unchanged."))
