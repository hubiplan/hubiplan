from django.db import migrations, models


class Migration(migrations.Migration):
    """Fassung gegen gleichzeitiges Bearbeiten (core/versioning.py): nur hinzugefügt, mit
    db_default; ältere Fassungen der Anwendung lesen und schreiben das Feld nicht.
    Rückweg: Migration zurücknehmen (Felder entfallen)."""

    dependencies = [
        ("competitions", "0023_lesbare_adressen"),
    ]

    operations = [
        migrations.AddField(
            model_name="scoring",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
        migrations.AddField(
            model_name="shootingprogram",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
        migrations.AddField(
            model_name="trophy",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
    ]
