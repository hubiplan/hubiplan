# Fachfrage FQ15 (Audit 02.11.): große offene Verteiler moderieren

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("circulars", "0012_verteiler_direkt"),
    ]

    operations = [
        migrations.AddField(
            model_name="mailinglist",
            name="open_direct_max",
            field=models.PositiveIntegerField(
                db_default=50, default=50, verbose_name="ohne Freigabe höchstens an"
            ),
        ),
    ]
