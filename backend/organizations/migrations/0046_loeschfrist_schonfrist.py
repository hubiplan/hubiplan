# Fachfrage FQ10 (Audit 02.11.): verkürzte Löschfrist gilt erst nach einer Schonfrist

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0045_hilfe"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformsettings",
            name="deletion_period_previous",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="vorige Löschfrist (Monate)"
            ),
        ),
        migrations.AddField(
            model_name="platformsettings",
            name="deletion_period_changed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Löschfrist verkürzt am"),
        ),
    ]
