import django.contrib.postgres.indexes
from django.db import migrations, models


class Migration(migrations.Migration):
    """Frühere Erneuerungsschlüssel je Verbindung (nur SHA-256; Gesamtaudit 15.11., MCP-04).
    Leere Liste mit Datenbank-Vorgabe, damit die vorige Fassung weiter Verbindungen anlegt."""

    dependencies = [
        ("mcpserver", "0002_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcpgrant",
            name="retired_refresh_hashes",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AddIndex(
            model_name="mcpgrant",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["retired_refresh_hashes"], name="mcpgrant_retired_gin"
            ),
        ),
    ]
