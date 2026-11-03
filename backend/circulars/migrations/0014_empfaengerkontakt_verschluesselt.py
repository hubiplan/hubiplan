import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("circulars", "0013_offen_freigabe"),
    ]

    operations = [
        migrations.AlterField(
            model_name="circularrecipient",
            name="email",
            field=core.encfields.EncryptedEmailField(blank=True, verbose_name="E-Mail"),
        ),
    ]
