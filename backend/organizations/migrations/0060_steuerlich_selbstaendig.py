from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0059_module_weitergabe")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="tax_independent",
            # db_default: Ältere Fassungen (Rückweg) legen Einheiten ohne die Spalte an
            field=models.BooleanField("steuerlich selbständig", default=False, db_default=False),
        ),
    ]
