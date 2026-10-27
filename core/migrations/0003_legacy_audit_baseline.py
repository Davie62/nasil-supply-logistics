from django.db import migrations


def baseline(apps, schema_editor):
    AuditRecord = apps.get_model("core", "AuditRecord")
    using = schema_editor.connection.alias
    for model_name in ("quotations.Quote", "shipments.Shipment"):
        Model = apps.get_model(model_name)
        for instance in Model.objects.using(using).iterator():
            AuditRecord.objects.using(using).create(
                quote_id=instance.pk if model_name == "quotations.Quote" else instance.quote_id,
                shipment_id=instance.pk if model_name == "shipments.Shipment" else None,
                actor_label="Migration / legacy import", action="legacy_snapshot",
                to_status=instance.status, object_version=instance.version,
                reason="State observed at workflow rollout. Earlier approvals and transitions are unverified; historical actors and event timestamps are unknown.",
                changes={field.attname: {"before": None, "after": str(getattr(instance, field.attname)) if getattr(instance, field.attname) is not None else None} for field in instance._meta.concrete_fields},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_auditrecord"),
        ("quotations", "0002_alter_quote_options_quote_approved_at_and_more"),
        ("shipments", "0002_shipment_cancelled_at_shipment_created_by_and_more"),
    ]
    operations = [migrations.RunPython(baseline, migrations.RunPython.noop)]
