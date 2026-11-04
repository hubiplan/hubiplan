import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


def baseline(apps, schema_editor):
    Assignment = apps.get_model("music", "Assignment")
    Notice = apps.get_model("music", "PerformanceNotice")
    rows = Assignment.objects.using(schema_editor.connection.alias).values_list(
        "pk", "organization_id", "status"
    )
    batch = []
    for pk, org, status in rows.iterator(chunk_size=1000):
        batch.append(
            Notice(
                assignment_id=pk, organization_id=org, last_status=status, fingerprint="baseline"
            )
        )
        if len(batch) == 1000:
            Notice.objects.using(schema_editor.connection.alias).bulk_create(batch)
            batch = []
    if batch:
        Notice.objects.using(schema_editor.connection.alias).bulk_create(batch)


class Migration(migrations.Migration):
    dependencies = [("music", "0009_musicianabsence")]

    operations = [
        migrations.AddField(
            model_name="performance",
            name="remind_days",
            field=models.PositiveSmallIntegerField(
                default=3, db_default=3, validators=[django.core.validators.MaxValueValidator(30)]
            ),
        ),
        migrations.CreateModel(
            name="PerformanceNotice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("fingerprint", models.CharField(blank=True, max_length=64)),
                ("reminder_fingerprint", models.CharField(blank=True, max_length=64)),
                ("last_status", models.CharField(blank=True, max_length=12)),
                ("attempted_at", models.DateTimeField(blank=True, null=True)),
                ("notified_at", models.DateTimeField(blank=True, null=True)),
                ("reminded_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assignment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notice",
                        to="music.assignment",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="organizations.organization"
                    ),
                ),
            ],
        ),
        migrations.RunPython(baseline, migrations.RunPython.noop),
        migrations.RunSQL(
            enable_rls_sql("music_performancenotice"), disable_rls_sql("music_performancenotice")
        ),
    ]
