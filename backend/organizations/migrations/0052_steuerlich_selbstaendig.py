from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("organizations", "0051_adressen_je_einheit")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="tax_independent",
            # db_default: Ältere Fassungen (Rückweg) legen Einheiten ohne die Spalte an
            field=models.BooleanField("steuerlich selbständig", default=False, db_default=False),
        ),
    ]
