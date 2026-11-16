from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_liveness_is_public_and_ok(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @override_settings(HEALTHCHECK_BROKER=False)
    def test_readiness_reports_database(self):
        response = self.client.get(reverse("readyz"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checks"]["database"], "ok")
        self.assertNotIn("broker", payload["checks"])

    @override_settings(HEALTHCHECK_BROKER=False)
    @patch("core.views.connection.cursor", side_effect=Exception("database down"))
    def test_readiness_returns_503_when_database_fails(self, _cursor):
        response = self.client.get(reverse("readyz"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["database"], "error")

    @override_settings(HEALTHCHECK_BROKER=True)
    @patch("backend.celery.app.connection_for_read")
    def test_readiness_reports_broker_ok(self, connection_for_read):
        response = self.client.get(reverse("readyz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["broker"], "ok")
        connection_for_read.assert_called_once()

    @override_settings(HEALTHCHECK_BROKER=True)
    @patch("backend.celery.app.connection_for_read", side_effect=OSError("redis down"))
    def test_readiness_returns_503_when_broker_fails(self, _connection_for_read):
        response = self.client.get(reverse("readyz"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["broker"], "error")

    def test_probes_reject_non_get_methods(self):
        self.assertEqual(self.client.post(reverse("healthz")).status_code, 405)
        self.assertEqual(self.client.post(reverse("readyz")).status_code, 405)
