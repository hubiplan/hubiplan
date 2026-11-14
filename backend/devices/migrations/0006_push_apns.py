from django.db import migrations, models


class Migration(migrations.Migration):
    """Push-Weg „apns“ (iOS-App). Nur die Auswahl ändert sich, die Tabelle bleibt gleich."""

    dependencies = [
        ("devices", "0005_retired_hashes_gin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="push_kind",
            field=models.CharField(
                choices=[
                    ("none", "kein Push (Abruf)"),
                    ("unifiedpush", "UnifiedPush"),
                    ("fcm", "Google (FCM)"),
                    ("apns", "Apple (APNs)"),
                ],
                default="none",
                max_length=12,
            ),
        ),
    ]
