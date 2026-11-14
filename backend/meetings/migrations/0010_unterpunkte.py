# Unterpunkte in der Tagesordnung: Ebene und angezeigte Nummer je Punkt.
# db_default, damit die Fassung davor beim Rückweg weiter Punkte anlegen kann.

from django.db import migrations, models


def forwards(apps, schema_editor):
    from django.db.models.functions import Cast

    from core.tenancy import rls_bypass

    AgendaItem = apps.get_model("meetings", "AgendaItem")
    with rls_bypass():
        # Bisher gab es nur eine Ebene: Nummer = Position
        AgendaItem.objects.update(number=Cast("position", models.CharField()))


class Migration(migrations.Migration):
    dependencies = [("meetings", "0009_online_abstimmung")]

    operations = [
        migrations.AddField(
            model_name="agendaitem",
            name="level",
            field=models.PositiveSmallIntegerField(db_default=0, default=0),
        ),
        migrations.AddField(
            model_name="agendaitem",
            name="number",
            field=models.CharField(blank=True, db_default="", default="", max_length=10),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
