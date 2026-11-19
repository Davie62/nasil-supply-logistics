"""Operational readiness probe for schedulers and monitoring.

Unlike ``/healthz`` and ``/readyz``, this command verifies the pieces that are
easy to forget: unapplied migrations, object-storage access, the Celery broker
and the age of the newest encrypted backup.
"""
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from core import backup

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"


def check_database():
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        return OK, "database reachable"
    except Exception as error:  # pragma: no cover - depends on a live server
        return FAIL, f"database unreachable ({error.__class__.__name__})"


def check_migrations():
    try:
        executor = MigrationExecutor(connections["default"])
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception as error:  # pragma: no cover - depends on a live server
        return FAIL, f"migration state unreadable ({error.__class__.__name__})"
    if plan:
        return FAIL, f"{len(plan)} unapplied migration(s)"
    return OK, "migrations applied"


def check_broker():
    if not settings.HEALTHCHECK_BROKER:
        return SKIP, "broker check disabled (HEALTHCHECK_BROKER=false)"
    from backend.celery import app

    connection = app.connection_for_read()
    try:
        connection.ensure_connection(max_retries=0, timeout=3)
        return OK, "Celery broker reachable"
    except Exception as error:  # pragma: no cover - depends on a live broker
        return FAIL, f"Celery broker unreachable ({error.__class__.__name__})"
    finally:
        connection.release()


def check_storage():
    probe = f"healthcheck/{uuid.uuid4().hex}.txt"
    try:
        name = default_storage.save(probe, ContentFile(b"nasil-healthcheck"))
        try:
            with default_storage.open(name, "rb") as handle:
                if handle.read() != b"nasil-healthcheck":
                    return FAIL, "media storage returned the wrong probe contents"
        finally:
            default_storage.delete(name)
        return OK, "media storage writable and readable"
    except Exception as error:  # pragma: no cover - depends on a live bucket
        return FAIL, f"media storage unavailable ({error.__class__.__name__})"


def check_backups():
    try:
        newest = backup.newest_backup(settings.BACKUP_DIRECTORY)
        if newest is None:
            return WARN, f"no backup found in {settings.BACKUP_DIRECTORY}"
        age = backup.backup_age_hours(newest)
    except backup.BackupError as error:
        return WARN, str(error)
    if age > settings.BACKUP_MAX_AGE_HOURS:
        return WARN, f"newest backup {newest.name} is {age:.1f}h old (limit {settings.BACKUP_MAX_AGE_HOURS}h)"
    return OK, f"newest backup {newest.name} is {age:.1f}h old"


CHECKS = (
    ("database", check_database),
    ("migrations", check_migrations),
    ("broker", check_broker),
    ("storage", check_storage),
    ("backup", check_backups),
)


class Command(BaseCommand):
    help = "Check database, migrations, broker, media storage and backup freshness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Treat warnings (missing or stale backup) as failures.",
        )
        parser.add_argument(
            "--skip-storage",
            action="store_true",
            help="Skip the media write probe, for example in a read-only maintenance window.",
        )

    def handle(self, *args, **options):
        results = []
        for name, check in CHECKS:
            if name == "storage" and options["skip_storage"]:
                results.append((name, SKIP, "skipped by --skip-storage"))
                continue
            try:
                status, message = check()
            except Exception as error:  # a probe must never crash the command
                status, message = FAIL, f"{name} check raised {error.__class__.__name__}"
            results.append((name, status, message))

        for name, status, message in results:
            self.stdout.write(f"[{status.upper():4}] {name:10} {message}")

        failures = [name for name, status, _ in results if status == FAIL]
        warnings = [name for name, status, _ in results if status == WARN]
        if failures:
            raise CommandError(f"Operational health failed: {', '.join(failures)}.")
        if warnings and options["strict"]:
            raise CommandError(f"Operational health warnings: {', '.join(warnings)}.")
        self.stdout.write(self.style.SUCCESS("Operational health checks completed."))
