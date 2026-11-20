from django.db import migrations, models


class Migration(migrations.Migration):
    """Widerspruch gegen Glückwünsche: leeres Feld, ältere Fassungen lesen und schreiben es nicht.
    Rückweg: Migration zurücknehmen (Feld entfällt)."""

    dependencies = [
        ("members", "0036_hinweis_volljaehrigkeit"),
    ]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="greetings_opt_out_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Glückwünschen widersprochen am"
            ),
        ),
    ]
