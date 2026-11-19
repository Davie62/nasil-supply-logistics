"""Celery scheduling: every periodic entry must resolve to a real task."""
from django.conf import settings
from django.test import SimpleTestCase

from backend.celery import app


class BeatScheduleTests(SimpleTestCase):
    # Importing task modules loads models, whose field checks read DB features.
    databases = {"default"}

    def test_every_scheduled_task_is_registered(self):
        # Autodiscovery is lazy; force it before comparing names.
        app.loader.import_default_modules()
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertIn(entry["task"], app.tasks)

    def test_no_task_is_scheduled_twice(self):
        scheduled = [entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()]
        self.assertEqual(len(scheduled), len(set(scheduled)))

    def test_periodic_entries_use_a_sane_interval(self):
        # A sub-30-second cadence would hammer the outbox and provider APIs.
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertGreaterEqual(float(entry["schedule"]), 30.0)
