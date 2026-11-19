"""Encrypted backups: encryption, manifests, retention, commands and health checks."""
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from core import backup
from core.management.commands import check_operational_health


def backup_payload(path):
    manifest = {
        "format": backup.FORMAT,
        "created_at": datetime(2026, 11, 1, 12, 0, tzinfo=datetime_timezone.utc).isoformat(),
        "database_engine": "sqlite",
        "database_name": "db.sqlite3",
        "file": path.name,
        "ciphertext_sha256": backup.sha256_file(path),
        "ciphertext_bytes": path.stat().st_size,
        "plaintext_sha256": "0" * 64,
        "plaintext_bytes": 0,
    }
    return manifest


class BackupFileMixin:
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, True)

    def write_backup(self, moment, payload=b"database dump", label=""):
        path = self.directory / backup.backup_name(moment, label)
        plaintext = self.directory / "plaintext.tmp"
        plaintext.write_bytes(payload)
        backup.encrypt_stream(plaintext, path)
        plaintext.unlink()
        manifest = backup_payload(path)
        manifest["plaintext_sha256"] = backup.sha256_file(self._round_trip(path))
        backup.write_manifest(path, manifest)
        return path

    def _round_trip(self, path):
        restored = self.directory / "restored.tmp"
        backup.decrypt_stream(path, restored)
        self.addCleanup(restored.unlink, True)
        return restored


class EncryptionTests(BackupFileMixin, SimpleTestCase):
    def test_round_trip_preserves_bytes_across_chunks(self):
        source = self.directory / "source.bin"
        payload = b"nasil" * (backup.CHUNK_SIZE * 2 + 7)
        source.write_bytes(payload)
        encrypted = self.directory / "backup.dump.enc"
        restored = self.directory / "restored.bin"

        backup.encrypt_stream(source, encrypted)
        self.assertNotEqual(encrypted.read_bytes(), payload)
        self.assertTrue(encrypted.read_bytes().startswith(backup.MAGIC))
        backup.decrypt_stream(encrypted, restored)
        self.assertEqual(restored.read_bytes(), payload)

    def test_tampered_ciphertext_is_rejected(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        data = bytearray(path.read_bytes())
        data[-10] ^= 0xFF
        path.write_bytes(bytes(data))

        with self.assertRaises(backup.BackupError):
            backup.decrypt_stream(path, self.directory / "restored.bin")

    def test_decryption_with_a_different_key_fails_closed(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        with override_settings(SECURITY_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            with self.assertRaises(backup.BackupError):
                backup.decrypt_stream(path, self.directory / "restored.bin")

    def test_foreign_file_is_rejected(self):
        path = self.directory / "not-a-backup.dump.enc"
        path.write_bytes(b"PK\x03\x04 definitely not a NASIL backup")
        with self.assertRaises(backup.BackupError):
            backup.decrypt_stream(path, self.directory / "restored.bin")

    def test_truncated_block_is_rejected(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        path.write_bytes(path.read_bytes()[:-8])
        with self.assertRaises(backup.BackupError):
            backup.decrypt_stream(path, self.directory / "restored.bin")


class ManifestTests(BackupFileMixin, SimpleTestCase):
    def test_verify_accepts_an_intact_backup(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        manifest = backup.verify_backup(path)
        self.assertEqual(manifest["file"], path.name)

    def test_verify_detects_a_checksum_mismatch(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaisesMessage(backup.BackupError, "checksum"):
            backup.verify_backup(path)

    def test_missing_manifest_is_rejected(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        backup.manifest_path(path).unlink()
        with self.assertRaisesMessage(backup.BackupError, "Missing manifest"):
            backup.verify_backup(path)

    def test_missing_backup_is_rejected(self):
        with self.assertRaisesMessage(backup.BackupError, "not found"):
            backup.verify_backup(self.directory / "absent.dump.enc")

    def test_backup_name_is_sortable_and_labelled(self):
        moment = datetime(2026, 11, 19, 8, 30, 15, tzinfo=datetime_timezone.utc)
        self.assertEqual(backup.backup_name(moment), "nasil-20261119T083015Z.dump.enc")
        self.assertEqual(
            backup.backup_name(moment, "pre-upgrade"), "nasil-20261119T083015Z-pre-upgrade.dump.enc"
        )
        with self.assertRaises(backup.BackupError):
            backup.backup_name(moment, "Not Allowed!")

    def test_age_uses_the_manifest_timestamp(self):
        path = self.write_backup(datetime.now(datetime_timezone.utc))
        now = datetime(2026, 11, 1, 18, 0, tzinfo=datetime_timezone.utc)
        self.assertAlmostEqual(backup.backup_age_hours(path, now=now), 6.0, places=3)

    def test_retention_keeps_the_newest_backups_and_their_manifests(self):
        base = datetime(2026, 11, 1, 12, 0, tzinfo=datetime_timezone.utc)
        paths = [self.write_backup(base + timedelta(days=offset)) for offset in range(4)]

        removed = backup.prune_backups(self.directory, keep=2)

        self.assertEqual(sorted(removed), sorted(path.name for path in paths[:2]))
        self.assertEqual(backup.list_backups(self.directory), list(reversed(paths[2:])))
        for path in paths[:2]:
            self.assertFalse(path.exists())
            self.assertFalse(backup.manifest_path(path).exists())
        for path in paths[2:]:
            self.assertTrue(path.exists())
            self.assertTrue(backup.manifest_path(path).exists())

    def test_retention_rejects_zero(self):
        with self.assertRaises(backup.BackupError):
            backup.prune_backups(self.directory, keep=0)

    def test_newest_backup_returns_none_when_empty(self):
        self.assertIsNone(backup.newest_backup(self.directory))


class BackupCommandTests(BackupFileMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("core.backup.dump_database", side_effect=self.fake_dump)
        self.dump = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def fake_dump(destination):
        Path(destination).write_bytes(b"dump")
        return "sqlite"

    def run_command(self, **options):
        output = StringIO()
        call_command("backup_database", stdout=output, **options)
        return output.getvalue()

    def test_creates_an_encrypted_backup_with_a_manifest(self):
        output = self.run_command(output=self.directory, keep=3)

        backups = backup.list_backups(self.directory)
        self.assertEqual(len(backups), 1)
        self.assertIn("Backup written", output)
        manifest = backup.verify_backup(backups[0])
        self.assertEqual(manifest["database_engine"], "sqlite")
        restored = self.directory / "restored.dump"
        backup.decrypt_stream(backups[0], restored)
        self.assertEqual(restored.read_bytes(), b"dump")

    def test_prunes_old_backups_after_writing(self):
        base = datetime(2026, 11, 1, 12, 0, tzinfo=datetime_timezone.utc)
        for offset in range(3):
            self.write_backup(base + timedelta(days=offset))

        self.run_command(output=self.directory, keep=2)

        self.assertEqual(len(backup.list_backups(self.directory)), 2)

    def test_rejects_zero_retention(self):
        with self.assertRaisesMessage(CommandError, "at least one"):
            self.run_command(output=self.directory, keep=0)

    def test_dump_failure_becomes_a_command_error(self):
        self.dump.side_effect = backup.BackupError("pg_dump is not installed")
        with self.assertRaisesMessage(CommandError, "pg_dump is not installed"):
            self.run_command(output=self.directory, keep=3)


class RestoreCommandTests(BackupFileMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.live = self.directory / "live.sqlite3"
        config = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(self.live)}
        patcher = mock.patch("core.backup.database_config", return_value=config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = self.write_backup(datetime.now(datetime_timezone.utc))

    def run_restore(self, **options):
        call_command("restore_database", self.path, stdout=StringIO(), **options)

    def test_requires_confirmation(self):
        with self.assertRaisesMessage(CommandError, "--confirm"):
            self.run_restore(target_path=self.directory / "restored.sqlite3")

    @mock.patch("core.backup.restore_database", return_value="sqlite")
    def test_restores_into_an_isolated_target(self, restore):
        target = self.directory / "restored.sqlite3"
        self.run_restore(confirm=True, target_path=target)
        restore.assert_called_once()
        self.assertEqual(restore.call_args.kwargs["target_path"], target)

    def test_refuses_to_overwrite_the_live_database(self):
        with self.assertRaisesMessage(CommandError, "live database"):
            self.run_restore(confirm=True, target_path=self.live)

    def test_refuses_a_tampered_backup(self):
        self.path.write_bytes(self.path.read_bytes() + b"tampered")
        with self.assertRaisesMessage(CommandError, "checksum"):
            self.run_restore(confirm=True, target_path=self.directory / "restored.sqlite3")


class DatabaseHelperTests(BackupFileMixin, SimpleTestCase):
    POSTGRES = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "nasil",
        "USER": "nasil",
        "PASSWORD": "secret",
        "HOST": "db.internal",
        "PORT": "5432",
        "OPTIONS": {"sslmode": "verify-full", "sslrootcert": "/etc/ssl/ca.pem"},
    }

    def test_engine_names_are_recognised(self):
        self.assertEqual(backup.database_engine_name(self.POSTGRES), "postgresql")
        self.assertEqual(backup.database_engine_name({"ENGINE": "django.db.backends.sqlite3"}), "sqlite")
        with self.assertRaises(backup.BackupError):
            backup.database_engine_name({"ENGINE": "django.db.backends.mysql"})

    def test_sqlite_dump_copies_the_file(self):
        source = self.directory / "db.sqlite3"
        source.write_bytes(b"sqlite database")
        config = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(source)}

        with mock.patch("core.backup.database_config", return_value=config):
            engine = backup.dump_database(self.directory / "copy.dump")

        self.assertEqual(engine, "sqlite")
        self.assertEqual((self.directory / "copy.dump").read_bytes(), b"sqlite database")

    def test_sqlite_dump_rejects_a_missing_database(self):
        config = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(self.directory / "absent.sqlite3")}
        with mock.patch("core.backup.database_config", return_value=config):
            with self.assertRaisesMessage(backup.BackupError, "not found"):
                backup.dump_database(self.directory / "copy.dump")

    @mock.patch("core.backup.subprocess.run")
    def test_postgres_dump_keeps_the_password_out_of_argv(self, run):
        with mock.patch("core.backup.database_config", return_value=self.POSTGRES):
            engine = backup.dump_database(self.directory / "dump")

        self.assertEqual(engine, "postgresql")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "pg_dump")
        self.assertIn("--format=custom", command)
        self.assertEqual(command[-1], "nasil")
        self.assertNotIn("secret", " ".join(command))
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["PGPASSWORD"], "secret")
        self.assertEqual(environment["PGSSLMODE"], "verify-full")
        self.assertEqual(environment["PGSSLROOTCERT"], "/etc/ssl/ca.pem")

    @mock.patch("core.backup.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_pg_dump_is_reported(self, _run):
        with mock.patch("core.backup.database_config", return_value=self.POSTGRES):
            with self.assertRaisesMessage(backup.BackupError, "pg_dump is not installed"):
                backup.dump_database(self.directory / "dump")

    @mock.patch(
        "core.backup.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "pg_dump", stderr=b"connection refused\n"),
    )
    def test_pg_dump_failure_includes_the_reason(self, _run):
        with mock.patch("core.backup.database_config", return_value=self.POSTGRES):
            with self.assertRaisesMessage(backup.BackupError, "connection refused"):
                backup.dump_database(self.directory / "dump")

    @mock.patch("core.backup.subprocess.run")
    def test_postgres_restore_uses_pg_restore(self, run):
        source = self.directory / "dump"
        source.write_bytes(b"custom dump")
        with mock.patch("core.backup.database_config", return_value=self.POSTGRES):
            engine = backup.restore_database(source, target_name="nasil_restore")

        self.assertEqual(engine, "postgresql")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "pg_restore")
        self.assertIn("--clean", command)
        self.assertIn("--if-exists", command)
        self.assertEqual(command[command.index("--dbname") + 1], "nasil_restore")
        self.assertEqual(command[-1], str(source))

    def test_postgres_restore_requires_a_target(self):
        with mock.patch("core.backup.database_config", return_value=self.POSTGRES):
            with self.assertRaisesMessage(backup.BackupError, "--target-database"):
                backup.restore_database(self.directory / "dump")

    def test_postgres_restore_refuses_the_live_database(self):
        with mock.patch("core.backup.database_config", return_value=self.POSTGRES):
            with self.assertRaisesMessage(backup.BackupError, "live database"):
                backup.restore_database(self.directory / "dump", target_name="nasil")

    def test_sqlite_restore_refuses_the_live_database(self):
        live = self.directory / "live.sqlite3"
        live.write_bytes(b"live")
        config = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(live)}
        with mock.patch("core.backup.database_config", return_value=config):
            with self.assertRaisesMessage(backup.BackupError, "live SQLite"):
                backup.restore_database(self.directory / "dump", target_path=live)

    def test_sqlite_restore_compares_paths_even_when_the_target_is_absent(self):
        live = self.directory / "absent.sqlite3"
        config = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(live)}
        with mock.patch("core.backup.database_config", return_value=config):
            with self.assertRaisesMessage(backup.BackupError, "live SQLite"):
                backup.restore_database(self.directory / "dump", target_path=live)


class OperationalHealthCommandTests(SimpleTestCase):
    def run_command(self, checks, **options):
        output = StringIO()
        with mock.patch.object(check_operational_health, "CHECKS", checks):
            call_command("check_operational_health", stdout=output, **options)
        return output.getvalue()

    def test_all_ok_reports_success(self):
        checks = (("database", lambda: ("ok", "reachable")), ("backup", lambda: ("ok", "fresh")))
        output = self.run_command(checks)
        self.assertIn("[OK  ] database", output)
        self.assertIn("completed", output)

    def test_failure_exits_nonzero(self):
        checks = (("database", lambda: ("fail", "unreachable")),)
        with self.assertRaisesMessage(CommandError, "database"):
            self.run_command(checks)

    def test_warning_only_fails_in_strict_mode(self):
        checks = (("backup", lambda: ("warn", "stale")),)
        self.assertIn("[WARN]", self.run_command(checks))
        with self.assertRaisesMessage(CommandError, "backup"):
            self.run_command(checks, strict=True)

    def test_skip_storage_avoids_the_write_probe(self):
        def explode():
            raise AssertionError("storage probe must not run")

        checks = (("storage", explode),)
        output = self.run_command(checks, skip_storage=True)
        self.assertIn("[SKIP] storage", output)

    def test_unexpected_probe_error_is_reported_as_failure(self):
        def explode():
            raise RuntimeError("boom")

        checks = (("storage", explode),)
        with self.assertRaisesMessage(CommandError, "storage"):
            self.run_command(checks)
