# Name im Briefkopf mit eigenem Umbruch (Issue #487) und eigenes Logo (Issue #488). Nur neue Felder mit Grundwert in der
# Datenbank: die vorige Fassung läuft mit dieser Tabelle weiter.

from django.db import migrations, models

import letterhead.models
import organizations.models


class Migration(migrations.Migration):

    dependencies = [
        ("letterhead", "0005_briefbogen_gestaltung"),
    ]

    operations = [
        migrations.AddField(
            model_name="letterhead",
            name="logo",
            field=models.ImageField(
                blank=True,
                db_default="",
                default="",
                upload_to=letterhead.models.letterhead_logo_path,
                validators=[organizations.models.validate_logo],
                verbose_name="Logo für den Briefbogen",
            ),
        ),
        migrations.AddField(
            model_name="letterhead",
            name="head_name",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text="Höchstens zwei Zeilen; leer: der Name der Einheit.",
                max_length=200,
                verbose_name="Name im Briefkopf",
            ),
        ),
        migrations.AddField(
            model_name="letterhead",
            name="head_name_small",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Zweite Zeile kleiner"
            ),
        ),
    ]
