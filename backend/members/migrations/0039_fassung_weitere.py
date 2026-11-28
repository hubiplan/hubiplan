from django.db import migrations, models


class Migration(migrations.Migration):
    """Fassung gegen gleichzeitiges Bearbeiten (core/versioning.py): nur hinzugefügt, mit
    db_default; ältere Fassungen der Anwendung lesen und schreiben das Feld nicht.
    Rückweg: Migration zurücknehmen (Felder entfallen)."""

    dependencies = [
        ("members", "0038_mitgliedschaft_fassung"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipperiod",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
        migrations.AddField(
            model_name="departmentmembership",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
        migrations.AddField(
            model_name="contactperson",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
        migrations.AddField(
            model_name="billingaddress",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
        migrations.AddField(
            model_name="household",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
    ]
