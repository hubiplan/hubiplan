from django.db import migrations, models


class Migration(migrations.Migration):
    """Eigenes Kalender-Abo für die Termine „nur Vorstand“ (nur hinzugefügt,
    die Vorfassung liest die Spalte einfach nicht)."""

    dependencies = [
        ("events", "0016_infoschreiben"),
    ]

    operations = [
        migrations.AddField(
            model_name="personalcalendar",
            name="board_key_hash",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
