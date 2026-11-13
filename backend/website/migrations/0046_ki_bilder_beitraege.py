"""KI-Schnittstelle W2/W3: erlaubte Bildquellen, Hochladelinks und Beitragsentwürfe (mit RLS)."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLES = ["website_imageuploadlink", "website_socialdraft"]


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
        ("organizations", "0069_kuendigung"),
        ("website", "0045_titel_nennen"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="image_hosts",
            field=models.JSONField(
                blank=True,
                db_default=[],
                default=list,
                verbose_name="Erlaubte Bildquellen für KI-Assistenten",
            ),
        ),
        migrations.CreateModel(
            name="ImageUploadLink",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                (
                    "via",
                    models.CharField(blank=True, max_length=120, verbose_name="angelegt über"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(verbose_name="gültig bis")),
                ("max_files", models.PositiveSmallIntegerField(default=20)),
                ("uploaded", models.PositiveSmallIntegerField(default=0)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
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
                    "website",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="upload_links",
                        to="website.website",
                    ),
                ),
            ],
            options={
                "verbose_name": "Link zum Hochladen von Bildern",
                "verbose_name_plural": "Links zum Hochladen von Bildern",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SocialDraft",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "beliebig"),
                            ("instagram", "Instagram"),
                            ("facebook", "Facebook"),
                        ],
                        max_length=10,
                        verbose_name="Kanal",
                    ),
                ),
                ("text", models.TextField(max_length=2200, verbose_name="Text")),
                (
                    "images",
                    models.JSONField(blank=True, default=list, verbose_name="Bilder"),
                ),
                (
                    "via",
                    models.CharField(blank=True, max_length=120, verbose_name="angelegt über"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "done_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="erledigt am"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
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
                    "website",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_drafts",
                        to="website.website",
                    ),
                ),
            ],
            options={
                "verbose_name": "Entwurf eines Social-Media-Beitrags",
                "verbose_name_plural": "Entwürfe für Social-Media-Beiträge",
                "ordering": ["done_at", "-created_at", "-pk"],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
