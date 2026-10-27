from django.db import migrations, models


def initialize_sequences(apps, schema_editor):
    Profile = apps.get_model("accounts", "EmployeeProfile")
    Sequence = apps.get_model("accounts", "EmployeeIDSequence")
    alias = schema_editor.connection.alias
    Profile.objects.using(alias).filter(phone_number="").update(phone_number=None)
    for employee_id in Profile.objects.using(alias).values_list("employee_id", flat=True):
        parts = employee_id.rsplit("-", 2)
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            continue
        year, number = int(parts[1]), int(parts[2])
        sequence, _ = Sequence.objects.using(alias).get_or_create(year=year)
        if number > sequence.last_number:
            Sequence.objects.using(alias).filter(pk=year).update(last_number=number)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_initial")]
    operations = [
        migrations.AlterField(
            model_name="employeeprofile", name="phone_number",
            field=models.CharField(blank=True, default=None, max_length=20, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="EmployeeIDSequence",
            fields=[
                ("year", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.RunPython(initialize_sequences, migrations.RunPython.noop),
    ]
