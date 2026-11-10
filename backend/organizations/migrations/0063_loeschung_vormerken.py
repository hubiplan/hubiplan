# Zweistufiges Löschen von Einheiten (Gesamtaudit 10.11., F02)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0062_umsatzsteuer"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="erase_requested_at",
            field=models.DateTimeField(
                blank=True, editable=False, null=True, verbose_name="Löschung vorgemerkt am"
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="erase_requested_by",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Löschung vorgemerkt von",
            ),
        ),
    ]
