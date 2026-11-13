# Gesamtaudit 13.11.2026, S-03: Beleg des angenommenen Antrags als PDF, Angaben nach Frist weg

from django.db import migrations, models

import admission.models
import core.privatefiles
import exchange.models


class Migration(migrations.Migration):
    dependencies = [
        ("admission", "0001_antraege"),
    ]

    operations = [
        migrations.AddField(
            model_name="application",
            name="pdf",
            field=core.privatefiles.PrivateFileField(
                blank=True,
                storage=exchange.models.private_storage,
                upload_to=admission.models.application_pdf_path,
                verbose_name="PDF",
            ),
        ),
        migrations.AddField(
            model_name="application",
            name="data_purged_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Angaben entfernt am"),
        ),
    ]
