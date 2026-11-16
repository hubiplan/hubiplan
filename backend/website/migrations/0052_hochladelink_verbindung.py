import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Hochladelink an die KI-Verbindung gebunden (Gesamtaudit 15.11., MCP-06); leer für Links
    aus der Oberfläche und ältere Links, die vorige Fassung schreibt das Feld nicht."""

    dependencies = [
        ("mcpserver", "0002_rls"),
        ("website", "0051_db_default_rueckweg"),
    ]

    operations = [
        migrations.AddField(
            model_name="imageuploadlink",
            name="grant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="mcpserver.mcpgrant",
            ),
        ),
    ]
