# Videoraum am Termin (Talk)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("oidc", "0010_dateien"),
        ("events", "0017_vorstands_abo"),
        ("organizations", "0045_hilfe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="talk_enabled",
            field=models.BooleanField(
                db_default=False, default=False, verbose_name="Videoraum am Termin"
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="talk_keep_days",
            field=models.PositiveSmallIntegerField(
                db_default=7, default=7, verbose_name="Videoraum löschen nach … Tagen"
            ),
        ),
        migrations.CreateModel(
            name="TalkRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=64)),
                ("password", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="talk_rooms",
                        to="oidc.client",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "event",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="talk_room",
                        to="events.event",
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
            ],
            options={
                "verbose_name": "Videoraum",
                "verbose_name_plural": "Videoräume",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunSQL(enable_rls_sql("oidc_talkroom"), disable_rls_sql("oidc_talkroom")),
    ]
