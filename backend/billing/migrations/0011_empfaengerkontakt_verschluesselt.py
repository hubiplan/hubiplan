import core.encfields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0010_rechnung_anonymisiert"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="recipient_email",
            field=core.encfields.EncryptedEmailField(blank=True, verbose_name="E-Mail"),
        ),
    ]
