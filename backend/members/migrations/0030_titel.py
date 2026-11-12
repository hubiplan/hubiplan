"""Titel (Dr., Prof. …) an Person und Ansprechpartner; Werte aus einem Zusatzfeld
„Titel“ übernehmen. Abwärtsverträglich: neue Spalten mit Standardwert in der Datenbank."""

from django.db import migrations, models

def take_over(apps, schema_editor):
    from core.tenancy import rls_bypass
    from members.title import take_over_field

    with rls_bypass():
        take_over_field(
            apps.get_model("members", "Person"),
            apps.get_model("customfields", "FieldDefinition"),
            apps.get_model("customfields", "FieldValue"),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0029_geburtsdatum_freiwillig"),
        ("customfields", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="title",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=30,
                verbose_name="Titel",
            ),
        ),
        migrations.AddField(
            model_name="contactperson",
            name="title",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=30,
                verbose_name="Titel",
            ),
        ),
        migrations.RunPython(take_over, migrations.RunPython.noop),
    ]
