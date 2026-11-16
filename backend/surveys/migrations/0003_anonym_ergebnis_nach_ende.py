from django.db import migrations


def tighten(apps, schema_editor):
    """Laufende anonyme Umfragen zeigen ihr Ergebnis erst nach dem Ende (Gesamtaudit 15.11.,
    Fachfrage FF-22 (a)). Nur verschärfen: „nach der eigenen Antwort“ und „immer“ werden zu
    „nach dem Ende“; „nur für die Verwaltung“ bleibt."""
    Survey = apps.get_model("surveys", "Survey")
    Survey.objects.using(schema_editor.connection.alias).filter(names="anonymous").exclude(
        status="closed"
    ).filter(results__in=["always", "after_answer"]).update(results="after_close")


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0002_rls_rechte"),
    ]

    operations = [
        # Rückwärts nichts: eine gelockerte Sichtbarkeit wiederherzustellen, wäre genau der Fehler
        migrations.RunPython(tighten, migrations.RunPython.noop, elidable=True),
    ]
