"""Issue #707: eigene Beiträge unter „Aktuelles“ (mit RLS)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ["website_newspost"]


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
        ("organizations", "0078_koeder_ausloesungen"),
        ("website", "0056_social_ruecksprung_je_kanal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsPost",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("slug", models.CharField(max_length=80, verbose_name="Adresse")),
                ("title", models.CharField(max_length=120, verbose_name="Titel")),
                ("date", models.DateField(verbose_name="Datum")),
                ("body", models.TextField(blank=True, max_length=20000, verbose_name="Text")),
                ("images", models.JSONField(blank=True, default=list, verbose_name="Bilder")),
                ("videos", models.JSONField(blank=True, default=list, verbose_name="Videos")),
                ("published_title", models.CharField(blank=True, max_length=120)),
                ("published_date", models.DateField(blank=True, null=True)),
                ("published_body", models.TextField(blank=True)),
                ("published_images", models.JSONField(blank=True, default=list)),
                ("published_videos", models.JSONField(blank=True, default=list)),
                (
                    "published_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="veröffentlicht am"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.department",
                        verbose_name="Untereinheit",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
                (
                    "updated_by",
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
                        related_name="news_posts",
                        to="website.website",
                    ),
                ),
            ],
            options={
                "verbose_name": "Eigener Beitrag (Aktuelles)",
                "verbose_name_plural": "Eigene Beiträge (Aktuelles)",
                "ordering": ["-date", "-pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("website", "slug"), name="webseite_beitrag_adresse"
                    )
                ],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
