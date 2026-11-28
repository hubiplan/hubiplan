from django.db import migrations, models


class Migration(migrations.Migration):
    """Fassung gegen gleichzeitiges Bearbeiten (core/versioning.py): nur hinzugefügt, mit
    db_default; ältere Fassungen der Anwendung lesen und schreiben das Feld nicht.
    Rückweg: Migration zurücknehmen (Felder entfallen)."""

    dependencies = [
        ("access", "0018_geschaeftspartner"),
    ]

    operations = [
        migrations.AddField(
            model_name="roleassignment",
            name="version",
            field=models.PositiveIntegerField(
                db_default=1, default=1, editable=False, verbose_name="Fassung"
            ),
        ),
    ]
