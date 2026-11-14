"""Darstellung: Hell ist die Vorgabe, dunkel nur auf eigenen Wunsch.

Bisher war „Wie Gerät“ die Vorgabe, die jedes Konto ungefragt trug. Diese Konten werden auf
„Hell“ gestellt; wer ausdrücklich „Dunkel“ gewählt hat, behält es. Die vorige Fassung kommt mit
allen drei Werten zurecht (docs/releases.md), zurück ändert sich deshalb nichts an den Daten.
"""

from django.db import migrations, models


def auf_hell(apps, schema_editor):
    apps.get_model("accounts", "User").objects.filter(color_scheme="auto").update(
        color_scheme="light"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_startseite_anordnung"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="color_scheme",
            field=models.CharField(
                choices=[("auto", "Wie Gerät"), ("light", "Hell"), ("dark", "Dunkel")],
                db_default="light",
                default="light",
                max_length=5,
                verbose_name="Darstellung",
            ),
        ),
        migrations.RunPython(auf_hell, migrations.RunPython.noop),
    ]
