"""Fehlende Fristanker konservativ ergänzen; keine Originaldatei löschen."""

from django.db import migrations
from django.db.models import Max, Min, Q


def fill_dates(apps, schema_editor):
    statements = apps.get_model("finance", "BankStatement")
    for st in statements.objects.using(schema_editor.connection.alias).filter(
        Q(date_from__isnull=True) | Q(date_to__isnull=True)
    ).annotate(first_day=Min("lines__date"), last_day=Max("lines__date")).iterator():
        start = st.date_from or st.first_day or st.date_to or st.created_at.date()
        end = st.date_to or st.last_day or start
        statements.objects.using(schema_editor.connection.alias).filter(pk=st.pk).update(
            date_from=start, date_to=end
        )


class Migration(migrations.Migration):
    dependencies = [("finance", "0021_loeschsperre")]
    operations = [migrations.RunPython(fill_dates, migrations.RunPython.noop)]
