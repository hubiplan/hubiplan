"""Untereinheiten: Teilmenge der Module des Vereins (Modulverzeichnis, M5).

Neues Feld ``unit_hidden_modules``, leer = alle Module des Vereins; es ändert sich nichts.
Rückweg: Das Feld wird entfernt; Untereinheiten sehen dann wieder alle Module des Vereins.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0057_freigegebene_module")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="unit_hidden_modules",
            field=models.JSONField(
                blank=True,
                db_default=[],
                default=list,
                verbose_name="für diese Untereinheit ausgeblendete Module",
            ),
        ),
    ]
