"""Restore an encrypted backup into an isolated database, never the live one."""
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core import backup


class Command(BaseCommand):
    help = (
        "Verify and decrypt a backup, then restore it into an isolated PostgreSQL database "
        "or SQLite file. The live database is always refused."
    )

    def add_arguments(self, parser):
        parser.add_argument("backup", type=Path, help="Path to a nasil-*.dump.enc file.")
        parser.add_argument(
            "--target-database",
            default="",
            help="PostgreSQL database name to restore into (must not be the live database).",
        )
        parser.add_argument(
            "--target-path",
            type=Path,
            default=None,
            help="SQLite file to write the restored copy to.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required. Acknowledges that the target database will be dropped and recreated.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError(
                "Refusing to restore without --confirm. The target database will be dropped and recreated."
            )
        source = Path(options["backup"])
        config = backup.database_config()
        try:
            manifest = backup.verify_backup(source)
            engine = backup.database_engine_name(config)
            if engine == "postgresql":
                target = options["target_database"]
                if not target:
                    raise backup.BackupError("Pass --target-database for a PostgreSQL restore.")
                if target == config.get("NAME"):
                    raise backup.BackupError("Refusing to restore into the live database.")
            else:
                target = options["target_path"]
                if not target:
                    raise backup.BackupError("Pass --target-path for a SQLite restore.")
                if Path(target).resolve() == Path(config["NAME"]).resolve():
                    raise backup.BackupError("Refusing to restore into the live database.")
            with tempfile.TemporaryDirectory() as temporary:
                plaintext = Path(temporary) / "database.dump"
                backup.decrypt_stream(source, plaintext)
                if backup.sha256_file(plaintext) != manifest.get("plaintext_sha256"):
                    raise backup.BackupError("The decrypted dump does not match the manifest checksum.")
                backup.restore_database(
                    plaintext,
                    target_name=options["target_database"] or None,
                    target_path=options["target_path"],
                )
        except backup.BackupError as error:
            raise CommandError(str(error))

        self.stdout.write(self.style.SUCCESS(f"Restored {source.name} into {target}."))
        self.stdout.write(
            "Start the application against the restored copy, run `manage.py check` and the "
            "regression suite, then compare record counts before promoting it."
        )
