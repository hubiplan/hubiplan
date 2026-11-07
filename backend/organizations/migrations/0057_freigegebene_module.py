"""Freigabe und Einschalten trennen (Modulverzeichnis, M3).

Neues Feld ``released_modules``: was die Plattform freigibt. Für Dachverbände und Vereine
wird die Freigabe aus den heute eingeschalteten Modulen übernommen (Vereine mit Mitgliedern
dazu den Mitgliederbereich, den sie selbst schalten); damit ändert sich nichts.
Untereinheiten folgen weiter ihrem Verein.
Rückweg: Das Feld wird entfernt; ``enabled_modules`` bleibt unverändert.
"""

from django.db import migrations, models


def _bypass(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    for org in Organization.objects.filter(type__in=("federation", "club")):
        released = set(org.enabled_modules or [])
        # Den Mitgliederbereich schaltet der Verein selbst (Mitglieder › Einrichtung)
        if org.type == "club" and "members" in released:
            released.add("portal")
        org.released_modules = sorted(released)
        org.save(update_fields=["released_modules"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0056_schiesssport")]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="released_modules",
            field=models.JSONField(
                blank=True, db_default=[], default=list, verbose_name="freigegebene Module"
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="enabled_modules",
            field=models.JSONField(blank=True, default=list, verbose_name="eingeschaltete Module"),
        ),
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
