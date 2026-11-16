from django.db import migrations, models


class Migration(migrations.Migration):
    """Leeres Feld; ältere Fassungen lesen und schreiben es nicht (abwärtsverträglich)."""

    dependencies = [
        ("members", "0034_erziehungsberechtigte"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactperson",
            name="adult_notice_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Hinweis zur Volljährigkeit am"
            ),
        ),
    ]
