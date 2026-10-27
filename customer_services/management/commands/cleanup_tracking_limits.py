from django.core.management.base import BaseCommand
from django.utils import timezone
from customer_services.models import RateBucket


class Command(BaseCommand):
    help = "Remove expired public tracking and authentication rate-limit buckets."

    def handle(self, *args, **options):
        count, _ = RateBucket.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f"Removed {count} expired rate-limit buckets.")
