"""Webseite #149: lesbare Adressen für Würden (/majestaeten/hubertuskoenige/).

Rückweg: Die Felder entfallen; die Webseite zeigt dann wieder die Adressen mit Kennung, die sie
weiter kennt."""

from django.db import migrations, models

from core.plural import guess_plural
from core.webslug import backfill


def fill(apps, schema_editor):
    Dignity = apps.get_model("honors", "Dignity")
    backfill(
        Dignity.objects.all(),
        lambda d: d.name_plural.strip() or guess_plural(d.name) or d.name,
        "wuerde",
    )


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
    dependencies = [("honors", "0008_foto_einwilligung")]

    operations = [
        *fields("dignity"),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
