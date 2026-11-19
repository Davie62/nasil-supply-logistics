"""Configuration is evaluated independently of the running Django process."""
import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DeploymentConfigurationTests(SimpleTestCase):
    def settings(self, **environment):
        # settings.py loads the developer's .env file, which would otherwise
        # refill the cleared environment and silently defeat these checks.
        with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
            return runpy.run_path(str(Path(__file__).with_name("settings.py")))

    def production_environment(self):
        return {
            "DJANGO_SECRET_KEY": "long-private-test-key-" * 4,
            "DJANGO_ALLOWED_HOSTS": "logistics.example.com",
            "POSTGRES_DB": "nasil", "POSTGRES_USER": "nasil",
            "POSTGRES_PASSWORD": "test-only", "POSTGRES_HOST": "db.example.com",
            "SECURITY_ENCRYPTION_KEYS": "dGVzdC1vbmx5LW5vdC1hLXByb2R1Y3Rpb24ta2V5ISE=",
            "CELERY_BROKER_URL": "rediss://redis.example.com:6379/0",
            "AWS_STORAGE_BUCKET_NAME": "nasil-media-test",
            "AWS_S3_REGION_NAME": "eu-central-1",
        }

    def test_no_environment_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            self.settings()

    def test_explicit_development_uses_stable_key_and_sqlite(self):
        first = self.settings(DJANGO_DEBUG="true")
        second = self.settings(DJANGO_DEBUG="true")
        self.assertEqual(first["SECRET_KEY"], second["SECRET_KEY"])
        self.assertTrue(first["DEBUG"])
        self.assertEqual(first["DATABASES"]["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(first["QUOTATION_APPROVAL_THRESHOLDS"], {"UGX": "50000000.00", "USD": "15000.00"})

    def test_approval_policy_requires_a_json_object(self):
        for policy in ("invalid", "[]", "null"):
            with self.subTest(policy=policy), self.assertRaises(ImproperlyConfigured):
                self.settings(DJANGO_DEBUG="true", QUOTATION_APPROVAL_THRESHOLDS=policy)

    def test_development_media_uses_the_filesystem(self):
        settings = self.settings(DJANGO_DEBUG="true")
        self.assertEqual(settings["MEDIA_STORAGE_BACKEND"], "filesystem")
        self.assertEqual(settings["STORAGES"]["default"]["BACKEND"], "django.core.files.storage.FileSystemStorage")

    def test_production_requires_durable_private_media(self):
        environment = self.production_environment()
        for variable in ("AWS_STORAGE_BUCKET_NAME", "AWS_S3_REGION_NAME"):
            with self.subTest(variable=variable):
                incomplete = {key: value for key, value in environment.items() if key != variable}
                with self.assertRaises(ImproperlyConfigured):
                    self.settings(**incomplete)

    def test_production_media_is_private_s3_with_presigned_urls(self):
        settings = self.settings(**self.production_environment())
        media = settings["STORAGES"]["default"]
        self.assertEqual(media["BACKEND"], "storages.backends.s3.S3Storage")
        self.assertEqual(media["OPTIONS"]["bucket_name"], "nasil-media-test")
        self.assertEqual(media["OPTIONS"]["region_name"], "eu-central-1")
        self.assertEqual(media["OPTIONS"]["location"], "media")
        self.assertIsNone(media["OPTIONS"]["default_acl"])
        self.assertIsNone(media["OPTIONS"]["custom_domain"])
        self.assertTrue(media["OPTIONS"]["querystring_auth"])
        self.assertFalse(media["OPTIONS"]["file_overwrite"])
        self.assertEqual(settings["STORAGES"]["staticfiles"]["BACKEND"], "django.contrib.staticfiles.storage.StaticFilesStorage")

    def test_ephemeral_media_requires_explicit_acknowledgement(self):
        environment = {**self.production_environment(), "MEDIA_STORAGE_BACKEND": "filesystem"}
        with self.assertRaises(ImproperlyConfigured):
            self.settings(**environment)
        allowed = self.settings(**{**environment, "MEDIA_STORAGE_ALLOW_EPHEMERAL": "true"})
        self.assertEqual(allowed["STORAGES"]["default"]["BACKEND"], "django.core.files.storage.FileSystemStorage")

    def test_unsupported_media_backend_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            self.settings(**{**self.production_environment(), "MEDIA_STORAGE_BACKEND": "dropbox"})

    def test_presigned_url_lifetime_is_bounded(self):
        for value in ("30", "7200", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                self.settings(**{**self.production_environment(), "AWS_QUERYSTRING_EXPIRE": value})

    def test_production_has_https_postgresql_and_static_root(self):
        settings = self.settings(**self.production_environment())
        self.assertFalse(settings["DEBUG"])
        self.assertTrue(settings["SECURE_SSL_REDIRECT"])
        self.assertTrue(settings["SESSION_COOKIE_SECURE"])
        self.assertTrue(settings["CSRF_COOKIE_SECURE"])
        self.assertEqual(settings["DATABASES"]["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(settings["DATABASES"]["default"]["OPTIONS"]["sslmode"], "verify-full")
        self.assertIn("STATIC_ROOT", settings)
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", settings)

    def test_incomplete_or_unsafe_production_environment_is_rejected(self):
        for change in (
            {"DJANGO_SECRET_KEY": "short"}, {"DJANGO_SECRET_KEY": "django-insecure-" + "x" * 60},
            {"DJANGO_ALLOWED_HOSTS": ""}, {"DJANGO_ALLOWED_HOSTS": "*"},
            {"POSTGRES_PASSWORD": ""}, {"DJANGO_DB_ENGINE": "sqlite"},
            {"DJANGO_DB_ENGINE": "unsupported"},
            {"SECURITY_ENCRYPTION_KEYS": ""}, {"SECURITY_ENCRYPTION_KEYS": "invalid"},
            {"SECURITY_REQUIRE_STAFF_MFA": "false"}, {"CELERY_BROKER_URL": "redis://redis.example.com:6379/0"},
            {"POSTGRES_SSLMODE": "disable"}, {"SECURITY_TRUSTED_PROXY_NETWORKS": "invalid"},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ImproperlyConfigured):
                    self.settings(**{**self.production_environment(), **change})

    def test_forwarded_headers_require_explicit_trust(self):
        settings = self.settings(**{**self.production_environment(), "DJANGO_TRUST_PROXY": "true", "SECURITY_TRUSTED_PROXY_NETWORKS": "127.0.0.1/32"})
        self.assertEqual(settings["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_vercel_trusts_only_platform_deployment_hostnames(self):
        environment = {**self.production_environment(), "VERCEL": "1",
                       "DJANGO_ALLOWED_HOSTS": "", "VERCEL_URL": "nasil-demo-abc.vercel.app",
                       "VERCEL_BRANCH_URL": "https://invalid.vercel.app",
                       "VERCEL_PROJECT_PRODUCTION_URL": "nasil-supply-logistics.vercel.app"}
        settings = self.settings(**environment)
        self.assertEqual(settings["ALLOWED_HOSTS"], ["nasil-demo-abc.vercel.app", "nasil-supply-logistics.vercel.app"])
        self.assertIn("https://nasil-demo-abc.vercel.app", settings["CSRF_TRUSTED_ORIGINS"])
        self.assertNotIn(".vercel.app", settings["ALLOWED_HOSTS"])
        self.assertEqual(settings["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertEqual(settings["DATABASES"]["default"]["CONN_MAX_AGE"], 0)
        self.assertTrue(settings["DATABASES"]["default"]["DISABLE_SERVER_SIDE_CURSORS"])

    def test_vercel_metadata_is_ignored_outside_platform(self):
        settings = self.settings(**{**self.production_environment(), "VERCEL_URL": "foreign.vercel.app"})
        self.assertNotIn("foreign.vercel.app", settings["ALLOWED_HOSTS"])
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", settings)

    def test_neon_database_name_alias(self):
        environment = self.production_environment()
        environment.pop("POSTGRES_DB")
        settings = self.settings(**{**environment, "POSTGRES_DATABASE": "neondb"})
        self.assertEqual(settings["DATABASES"]["default"]["NAME"], "neondb")

    def test_backup_retention_and_age_are_validated(self):
        for variable in ("BACKUP_RETENTION_COUNT", "BACKUP_MAX_AGE_HOURS"):
            for value in ("0", "-3", "many"):
                with self.subTest(variable=variable, value=value), self.assertRaises(ImproperlyConfigured):
                    self.settings(**{**self.production_environment(), variable: value})

    def test_backup_settings_have_safe_defaults(self):
        settings = self.settings(**self.production_environment())
        self.assertEqual(settings["BACKUP_RETENTION_COUNT"], 14)
        self.assertEqual(settings["BACKUP_MAX_AGE_HOURS"], 26)
        self.assertTrue(str(settings["BACKUP_DIRECTORY"]).endswith("backups"))
