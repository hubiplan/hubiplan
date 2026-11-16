"""Webseite #149: lesbare Adressen für Reihen und Wettbewerbe (/ergebnisse/koenigsschiessen-2026/).

Rückweg: Die Felder entfallen; die Webseite zeigt dann wieder die Adressen mit Kennung, die sie
weiter kennt."""

from django.db import migrations, models

from core.webslug import backfill


def fill(apps, schema_editor):
    Series = apps.get_model("competitions", "Series")
    Competition = apps.get_model("competitions", "Competition")
    backfill(Series.objects.all(), lambda s: s.name, "reihe")

    def title(c):
        year = str(c.date.year) if c.date else ""
        return c.title if not year or year in c.title else f"{c.title} {year}"

    backfill(Competition.objects.all(), title, "wettbewerb")


def fields(model):
    return [
        migrations.AddField(
            model_name=model,
            name="web_slug",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=60,
                verbose_name="Adresse auf der Webseite",
            ),
        ),
        migrations.AddField(
            model_name=model,
            name="web_slug_auto",
            field=models.BooleanField(
                db_default=True, default=True, verbose_name="Adresse aus dem Namen"
            ),
        ),
        migrations.AddField(
            model_name=model,
            name="web_slug_history",
            field=models.JSONField(
                blank=True, db_default=[], default=list, verbose_name="frühere Adressen"
            ),
        ),
    ]


class Migration(migrations.Migration):
    dependencies = [("competitions", "0022_db_default_rueckweg")]

    operations = [
        *fields("series"),
        *fields("competition"),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
