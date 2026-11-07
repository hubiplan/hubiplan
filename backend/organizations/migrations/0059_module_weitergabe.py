"""Dachverband darf Module an seine Vereine weitergeben (Modulverzeichnis, M6).

Neues Feld ``modules_pass_down`` (Standard aus); es ändert sich nichts.
Rückweg: Das Feld wird entfernt; Freigaben gibt dann wieder nur die Plattform.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0058_untereinheit_module")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="modules_pass_down",
            field=models.BooleanField(
                db_default=False,
                default=False,
                verbose_name="darf Module an seine Vereine weitergeben",
            ),
        ),
    ]
