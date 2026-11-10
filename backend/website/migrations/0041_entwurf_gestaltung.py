"""Entwurf der Gestaltung und frühere Fassungen (Konzept webseite-baukasten G2)."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ["website_designversion"]


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(enable_rls_sql(table))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for table in TABLES:
            schema_editor.execute(disable_rls_sql(table))


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0047_schiessinfrastruktur"),
        ("website", "0040_stilregler"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="draft",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="Entwurf der Gestaltung"
            ),
        ),
        migrations.CreateModel(
            name="DesignVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("data", models.JSONField(default=dict)),
                ("published_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
                (
                    "published_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "website",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="design_versions",
                        to="website.website",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fassung der Gestaltung",
                "verbose_name_plural": "Fassungen der Gestaltung",
                "ordering": ["-published_at", "-pk"],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
