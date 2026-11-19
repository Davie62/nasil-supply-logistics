"""Create an encrypted, checksummed database backup and prune old copies."""
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core import backup


class Command(BaseCommand):
    help = (
        "Dump the database, encrypt it with the SECURITY_ENCRYPTION_KEYS ring, write a "
        "SHA-256 manifest, and delete backups beyond the retention count."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            default=None,
            help=f"Backup directory (default: {settings.BACKUP_DIRECTORY}).",
        )
        parser.add_argument(
            "--keep",
            type=int,
            default=None,
            help=f"Backups to retain (default: {settings.BACKUP_RETENTION_COUNT}).",
        )
        parser.add_argument(
            "--label",
            default="",
            help="Optional lowercase label appended to the filename, for example pre-upgrade.",
        )

    def handle(self, *args, **options):
        output = Path(options["output"] or settings.BACKUP_DIRECTORY)
        keep = options["keep"] if options["keep"] is not None else settings.BACKUP_RETENTION_COUNT
        if keep < 1:
            raise CommandError("--keep must keep at least one backup.")

        try:
            output.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as error:
            raise CommandError(f"Cannot create the backup directory {output}: {error.strerror or error}.") from None

        created = False
        destination = None
        try:
            moment = timezone.now()
            destination = output / backup.backup_name(moment, options["label"])
            if destination.exists():
                raise backup.BackupError(
                    "A backup with this timestamp already exists. Wait one second or pass a label."
                )
            with tempfile.TemporaryDirectory() as temporary:
                plaintext = Path(temporary) / "database.dump"
                engine = backup.dump_database(plaintext)
                plaintext_sha256 = backup.sha256_file(plaintext)
                plaintext_bytes = plaintext.stat().st_size
                created = True
                backup.encrypt_stream(plaintext, destination)

            destination.chmod(0o600)
            manifest = {
                "format": backup.FORMAT,
                "created_at": moment.isoformat(),
                "database_engine": engine,
                "database_name": str(backup.database_config().get("NAME", "")),
                "file": destination.name,
                "ciphertext_sha256": backup.sha256_file(destination),
                "ciphertext_bytes": destination.stat().st_size,
                "plaintext_sha256": plaintext_sha256,
                "plaintext_bytes": plaintext_bytes,
            }
            manifest_file = backup.write_manifest(destination, manifest)
            manifest_file.chmod(0o600)
            removed = backup.prune_backups(output, keep)
        except OSError:
            if created:
                destination.unlink(missing_ok=True)
            raise CommandError("The backup manifest could not be written; the partial backup was removed.") from None
        except backup.BackupError as error:
            if created:
                destination.unlink(missing_ok=True)
            raise CommandError(str(error))

        self.stdout.write(self.style.SUCCESS(f"Backup written: {destination}"))
        self.stdout.write(
            f"  engine={engine} plaintext={plaintext_bytes} bytes "
            f"ciphertext={manifest['ciphertext_bytes']} bytes sha256={manifest['ciphertext_sha256'][:16]}..."
        )
        if removed:
            self.stdout.write(f"  pruned {len(removed)} backup(s): {', '.join(removed)}")
