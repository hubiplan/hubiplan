# Social-Media-Beiträge: Likes, Kommentarzahl und (optional) Kommentartexte

import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql

TABLE = "website_socialcomment"


def rls_on(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql(TABLE))


def rls_off(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql(TABLE))


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
        ("website", "0056_social_ruecksprung_je_kanal"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialfeed",
            name="show_counts",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Likes und Kommentarzahl zeigen"
            ),
        ),
        migrations.AddField(
            model_name="socialfeed",
            name="comments",
            field=models.CharField(
                choices=[
                    ("off", "nicht zeigen"),
                    ("approval", "erst nach Freigabe"),
                    ("auto", "automatisch zeigen"),
                ],
                db_default="off",
                default="off",
                max_length=10,
                verbose_name="Kommentare",
            ),
        ),
        migrations.AddField(
            model_name="socialfeed",
            name="comments_granted",
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="like_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="comment_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SocialComment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("external_id", models.CharField(max_length=80)),
                ("author", models.CharField(blank=True, max_length=120, verbose_name="Von")),
                ("text", models.TextField(max_length=1000, verbose_name="Text")),
                ("published_at", models.DateTimeField()),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("visible", "sichtbar"),
                            ("pending", "wartet auf Freigabe"),
                            ("hidden", "ausgeblendet"),
                        ],
                        default="pending",
                        max_length=10,
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
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="comments",
                        to="website.socialpost",
                    ),
                ),
            ],
            options={
                "verbose_name": "Kommentar zu einem Social-Media-Beitrag",
                "verbose_name_plural": "Kommentare zu Social-Media-Beiträgen",
                "ordering": ["post_id", "published_at", "pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("post", "external_id"), name="socialcomment_unique"
                    )
                ],
            },
        ),
        migrations.RunPython(rls_on, rls_off),
    ]
