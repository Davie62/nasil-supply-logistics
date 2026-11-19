"""Encrypted, verifiable database backup primitives.

The management commands in ``core.management.commands`` orchestrate ``pg_dump``
and ``pg_restore``; this module owns the parts that must be tested without a
live PostgreSQL server: streaming encryption, manifests, checksums and
retention pruning.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import connections
from django.utils import timezone

BACKUP_SUFFIX = ".dump.enc"
MANIFEST_SUFFIX = ".manifest.json"
MAGIC = b"NASILBK1\n"
FORMAT = "nasil-backup/1"
CHUNK_SIZE = 1024 * 1024
# A Fernet token adds a fixed header/MAC plus base64 expansion to its payload.
MAX_TOKEN_SIZE = CHUNK_SIZE * 2
NAME_PATTERN = re.compile(r"^nasil-(?P<stamp>\d{8}T\d{6}Z)(?:-(?P<label>[a-z0-9-]{1,32}))?\.dump\.enc$")
LABEL_PATTERN = re.compile(r"^[a-z0-9-]{1,32}$")


class BackupError(Exception):
    """A backup cannot be created, verified or restored safely."""


def cipher():
    return MultiFernet([Fernet(key.encode()) for key in settings.SECURITY_ENCRYPTION_KEYS])


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_name(moment, label=""):
    if label and not LABEL_PATTERN.fullmatch(label):
        raise BackupError("The backup label may contain only a-z, 0-9 and hyphens (max 32).")
    stamp = moment.astimezone(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{label}" if label else ""
    return f"nasil-{stamp}{suffix}{BACKUP_SUFFIX}"


def manifest_path(backup_path):
    backup_path = Path(backup_path)
    if not backup_path.name.endswith(BACKUP_SUFFIX):
        raise BackupError("Backup files must end with .dump.enc.")
    return backup_path.with_name(backup_path.name[: -len(BACKUP_SUFFIX)] + MANIFEST_SUFFIX)


def encrypt_stream(source, destination):
    """Encrypt ``source`` into ``destination`` with a chunked, authenticated format."""
    multi = cipher()
    with open(source, "rb") as reader, open(destination, "wb") as writer:
        writer.write(MAGIC)
        for block in iter(lambda: reader.read(CHUNK_SIZE), b""):
            token = multi.encrypt(block)
            writer.write(len(token).to_bytes(4, "big"))
            writer.write(token)


def decrypt_stream(source, destination):
    """Decrypt a backup created by :func:`encrypt_stream`."""
    multi = cipher()
    with open(source, "rb") as reader, open(destination, "wb") as writer:
        if reader.read(len(MAGIC)) != MAGIC:
            raise BackupError("The file is not a NASIL backup.")
        while True:
            header = reader.read(4)
            if not header:
                break
            if len(header) != 4:
                raise BackupError("The backup is truncated.")
            size = int.from_bytes(header, "big")
            if not 0 < size <= MAX_TOKEN_SIZE:
                raise BackupError("The backup contains an invalid encrypted block.")
            token = reader.read(size)
            if len(token) != size:
                raise BackupError("The backup is truncated.")
            try:
                writer.write(multi.decrypt(token))
            except InvalidToken:
                raise BackupError(
                    "The backup cannot be decrypted. It was corrupted or encrypted with a key "
                    "that is no longer in SECURITY_ENCRYPTION_KEYS."
                ) from None


def write_manifest(backup_path, payload):
    path = manifest_path(backup_path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_manifest(backup_path):
    path = manifest_path(backup_path)
    if not path.exists():
        raise BackupError(f"Missing manifest: {path.name}.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise BackupError(f"Unreadable manifest: {path.name}.") from None
    if payload.get("format") != FORMAT:
        raise BackupError(f"Unsupported manifest format in {path.name}.")
    return payload


def verify_backup(backup_path):
    """Verify the manifest checksum before a restore touches any database."""
    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise BackupError(f"Backup not found: {backup_path}.")
    payload = read_manifest(backup_path)
    if payload.get("file") != backup_path.name:
        raise BackupError("The manifest does not describe this backup file.")
    if payload.get("ciphertext_sha256") != sha256_file(backup_path):
        raise BackupError("The backup checksum does not match its manifest. Do not restore it.")
    return payload


def list_backups(directory):
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.is_file() and NAME_PATTERN.fullmatch(path.name)),
        key=lambda path: path.name,
        reverse=True,
    )


def prune_backups(directory, keep):
    """Delete the oldest backups beyond ``keep`` and their manifests."""
    if keep < 1:
        raise BackupError("Retention must keep at least one backup.")
    removed = []
    for path in list_backups(directory)[keep:]:
        path.unlink()
        manifest = manifest_path(path)
        if manifest.exists():
            manifest.unlink()
        removed.append(path.name)
    return removed


def newest_backup(directory):
    backups = list_backups(directory)
    return backups[0] if backups else None


def backup_age_hours(backup_path, now=None):
    payload = read_manifest(backup_path)
    created = payload.get("created_at")
    if not created:
        raise BackupError("The manifest has no creation time.")
    try:
        moment = datetime.fromisoformat(created)
    except ValueError:
        raise BackupError("The manifest creation time is invalid.") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime_timezone.utc)
    return ((now or timezone.now()) - moment).total_seconds() / 3600


def database_config():
    return connections["default"].settings_dict


def database_engine_name(config):
    engine = config.get("ENGINE", "")
    if "postgresql" in engine:
        return "postgresql"
    if "sqlite3" in engine:
        return "sqlite"
    raise BackupError(f"Unsupported database engine for backup: {engine or 'unknown'}.")


def _postgres_environment(config):
    environment = os.environ.copy()
    if config.get("PASSWORD"):
        environment["PGPASSWORD"] = config["PASSWORD"]
    options = config.get("OPTIONS") or {}
    if options.get("sslmode"):
        environment["PGSSLMODE"] = options["sslmode"]
    if options.get("sslrootcert"):
        environment["PGSSLROOTCERT"] = options["sslrootcert"]
    return environment


def _postgres_connection_arguments(config):
    arguments = []
    if config.get("HOST"):
        arguments += ["--host", config["HOST"]]
    if config.get("PORT"):
        arguments += ["--port", str(config["PORT"])]
    if config.get("USER"):
        arguments += ["--username", config["USER"]]
    return arguments


def dump_database(destination):
    """Write a consistent database dump to ``destination``."""
    config = database_config()
    engine = database_engine_name(config)
    if engine == "sqlite":
        source = Path(config["NAME"])
        if not source.exists() or not source.is_file():
            raise BackupError(f"SQLite database not found: {source}.")
        shutil.copyfile(source, destination)
        return engine
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        *_postgres_connection_arguments(config),
        "--file",
        str(destination),
        config["NAME"],
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, env=_postgres_environment(config))
    except FileNotFoundError:
        raise BackupError("pg_dump is not installed or not on PATH.") from None
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise BackupError(f"pg_dump failed: {detail[-1] if detail else error.returncode}") from None
    return engine


def restore_database(source, target_name=None, target_path=None):
    """Restore a plain dump produced by :func:`dump_database`."""
    config = database_config()
    engine = database_engine_name(config)
    if engine == "sqlite":
        if not target_path:
            raise BackupError("Pass --target-path for a SQLite restore.")
        target = Path(target_path)
        if target.resolve() == Path(config["NAME"]).resolve():
            raise BackupError("Refusing to overwrite the live SQLite database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return engine
    if not target_name:
        raise BackupError("Pass --target-database for a PostgreSQL restore.")
    if target_name == config.get("NAME"):
        raise BackupError("Refusing to restore into the live database.")
    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        *_postgres_connection_arguments(config),
        "--dbname",
        target_name,
        str(source),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, env=_postgres_environment(config))
    except FileNotFoundError:
        raise BackupError("pg_restore is not installed or not on PATH.") from None
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise BackupError(f"pg_restore failed: {detail[-1] if detail else error.returncode}") from None
    return engine
