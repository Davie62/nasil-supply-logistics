from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_auditlog"),
        ("core", "0003_legacy_audit_baseline"),
    ]

    operations = []
