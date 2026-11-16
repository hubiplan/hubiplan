from django.db import migrations, models


class Migration(migrations.Migration):
    """Neue Tabelle; ältere Fassungen lesen und schreiben sie nicht (abwärtsverträglich)."""

    dependencies = [
        ("core", "0039_quarantaene"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
                ("task", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_started_at", models.DateTimeField(blank=True, null=True)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=500)),
            ],
            options={
                "verbose_name": "Joblauf",
                "verbose_name_plural": "Jobläufe",
            },
        ),
    ]
