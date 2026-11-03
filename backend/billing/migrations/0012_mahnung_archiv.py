import billing.models
import core.privatefiles
import exchange.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0011_empfaengerkontakt_verschluesselt")]
    operations = [
        migrations.AddField(
            model_name="dunning",
            name="issued_pdf",
            field=core.privatefiles.PrivateFileField(
                blank=True,
                db_default="",
                storage=exchange.models.private_storage,
                upload_to=billing.models.dunning_pdf_path,
            ),
        ),
        migrations.AddField(
            model_name="dunning",
            name="issued_pdf_sha256",
            field=models.CharField(blank=True, db_default="", max_length=64),
        ),
    ]
