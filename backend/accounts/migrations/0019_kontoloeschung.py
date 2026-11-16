from django.db import migrations, models


class Migration(migrations.Migration):
    """Zwei leere Felder; ältere Fassungen lesen und schreiben sie nicht (abwärtsverträglich)."""

    dependencies = [
        ("accounts", "0018_zusatzadressen_entfernen"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="orphaned_since",
            field=models.DateTimeField(blank=True, null=True, verbose_name="ohne Zugang seit"),
        ),
        migrations.AddField(
            model_name="user",
            name="deletion_notice_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Hinweis zur Löschung am"
            ),
        ),
    ]
