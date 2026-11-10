from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_rls_zweckbindung"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuarantinedFile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=500, unique=True)),
                ("org_id", models.BigIntegerField(blank=True, null=True)),
                ("label", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "wartet auf Prüfung"),
                            ("infected", "Schadsoftware gefunden"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("signature", models.CharField(blank=True, default="", max_length=200)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("checked_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Datei in Quarantäne",
                "verbose_name_plural": "Dateien in Quarantäne",
                "indexes": [
                    models.Index(fields=["status", "checked_at"], name="core_quarantaene_status")
                ],
            },
        ),
    ]
