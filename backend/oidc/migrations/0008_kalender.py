# Termine per CalDAV in Kalender der Nextcloud schreiben (nur lesend freigegeben)

import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("oidc", "0007_pkce_pflicht"),
        ("organizations", "0045_hilfe"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="calendar_members",
            field=models.BooleanField(
                default=False,
                db_default=False,
                verbose_name="Termine für Mitglieder in die Nextcloud",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="calendar_members_group",
            field=models.CharField(
                blank=True,
                default="Mitglieder",
                db_default="Mitglieder",
                max_length=64,
                verbose_name="Gruppe für die Termine",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="calendar_board",
            field=models.BooleanField(
                default=False,
                db_default=False,
                verbose_name="Termine „nur Vorstand“ in die Nextcloud",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="calendar_board_group",
            field=models.CharField(
                blank=True,
                default="Vorstand",
                db_default="Vorstand",
                max_length=64,
                verbose_name="Gruppe für die Vorstandstermine",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="calendar_error",
            field=models.CharField(blank=True, db_default="", default="", max_length=500),
        ),
        migrations.AddField(
            model_name="client",
            name="calendar_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="CalendarItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("members", "Mitglieder"), ("board", "Vorstand")], max_length=10
                    ),
                ),
                ("name", models.CharField(max_length=80)),
                ("digest", models.CharField(max_length=64)),
                ("written_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calendar_items",
                        to="oidc.client",
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
                "verbose_name": "Termin in der Nextcloud",
                "verbose_name_plural": "Termine in der Nextcloud",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("client", "kind", "name"), name="oidc_calendaritem_unique"
                    )
                ],
            },
        ),
        migrations.RunSQL(
            enable_rls_sql("oidc_calendaritem"), disable_rls_sql("oidc_calendaritem")
        ),
    ]
