import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0033_datenschluessel_generationen")]

    operations = [
        migrations.CreateModel(
            name="DataKeyRotation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        primary_key=True, serialize=False, auto_created=True, verbose_name="ID"
                    ),
                ),
                ("source_key_ids", models.JSONField(default=list)),
                ("token", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
                ("phase", models.CharField(max_length=20, default="database")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="organizations.organization"
                    ),
                ),
                (
                    "target_key",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="+",
                        to="core.datakey",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization",),
                        condition=models.Q(completed_at__isnull=True),
                        name="core_ein_offener_schluesselwechsel",
                    )
                ],
            },
        ),
        migrations.RunSQL(
            sql=migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM core_datakeyrotation) THEN
                        RAISE EXCEPTION 'Schlüsselwechsel-Aufträge für Wiederaufnahme '
                            'und Nachweis erhalten; Rückmigration nicht möglich.';
                    END IF;
                END $$;
            """,
        ),
    ]
