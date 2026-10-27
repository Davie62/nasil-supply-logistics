"""Configuration is evaluated independently of the running Django process."""
import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DeploymentConfigurationTests(SimpleTestCase):
    def settings(self, **environment):
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(Path(__file__).with_name("settings.py")))

    def production_environment(self):
        return {
            "DJANGO_SECRET_KEY": "long-private-test-key-" * 4,
            "DJANGO_ALLOWED_HOSTS": "logistics.example.com",
            "POSTGRES_DB": "nasil", "POSTGRES_USER": "nasil",
            "POSTGRES_PASSWORD": "test-only", "POSTGRES_HOST": "db.example.com",
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
        ):
            with self.subTest(change=change):
                with self.assertRaises(ImproperlyConfigured):
                    self.settings(**{**self.production_environment(), **change})

    def test_forwarded_headers_require_explicit_trust(self):
        settings = self.settings(**{**self.production_environment(), "DJANGO_TRUST_PROXY": "true"})
        self.assertEqual(settings["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))
