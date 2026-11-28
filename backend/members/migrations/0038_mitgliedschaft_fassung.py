from django.db import migrations, models


class Migration(migrations.Migration):
    """Fassung gegen gleichzeitiges Bearbeiten (core/versioning.py): nur hinzugefügt, mit
    db_default; ältere Fassungen der Anwendung lesen und schreiben das Feld nicht.
    Rückweg: Migration zurücknehmen (Feld entfällt)."""

    dependencies = [
        ("members", "0037_widerspruch_glueckwuensche"),
    ]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
    ]
