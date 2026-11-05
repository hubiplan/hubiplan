"""E-Mail-Wechsel ohne Passwort: Bestätigung auch über die bisherige Adresse (GA-10)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_auth_version")]

    operations = [
        migrations.AddField(
            model_name="emailchange",
            name="old_token_hash",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="emailchange",
            name="new_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailchange",
            name="old_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
