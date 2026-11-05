import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


def migrate_programs(apps, schema_editor):
    Scoring = apps.get_model("competitions", "Scoring")
    Program = apps.get_model("competitions", "ShootingProgram")
    Hit = apps.get_model("competitions", "Hit")
    Score = apps.get_model("competitions", "Score")
    for scoring in Scoring.objects.filter(
        kind="einzel", competition__own=True, competition__form="rangliste"
    ).iterator():
        program = Program.objects.create(
            organization_id=scoring.organization_id,
            competition_id=scoring.competition_id,
            name=scoring.name,
            sort_order=scoring.sort_order,
            target=scoring.target,
            custom_target=scoring.custom_target,
            shots=scoring.shots,
        )
        Scoring.objects.filter(pk=scoring.pk).update(program_id=program.pk)
        Hit.objects.filter(scoring_id=scoring.pk).update(program_id=program.pk)
        Score.objects.filter(
            scoring_id=scoring.pk,
            starter_id__in=Hit.objects.filter(program_id=program.pk).values("starter_id"),
        ).update(from_hits=True)


def rls(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(enable_rls_sql("competitions_shootingprogram"))


def undo_rls(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(disable_rls_sql("competitions_shootingprogram"))


class Migration(migrations.Migration):
    dependencies = [("competitions", "0018_webseite_preisplaetze")]
    operations = [
        migrations.CreateModel(
            name="ShootingProgram",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "name",
                    models.CharField("Bezeichnung", max_length=100, default="Schießdurchgang"),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("target", models.CharField("Scheibe", max_length=30, blank=True)),
                ("custom_target", models.JSONField("eigene Scheibe", default=dict, blank=True)),
                (
                    "shots",
                    models.PositiveSmallIntegerField("Schüsse je Person", null=True, blank=True),
                ),
                ("position", models.CharField("Anschlagart", max_length=100, blank=True)),
                (
                    "distance",
                    models.PositiveSmallIntegerField("Entfernung in m", null=True, blank=True),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="organizations.organization"
                    ),
                ),
                (
                    "competition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="programs",
                        to="competitions.competition",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "pk"],
                "verbose_name": "Schießdurchgang",
                "verbose_name_plural": "Schießdurchgänge",
            },
        ),
        migrations.AddField(
            model_name="scoring",
            name="program",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                null=True,
                blank=True,
                related_name="scorings",
                to="competitions.shootingprogram",
            ),
        ),
        migrations.AddField(
            model_name="hit",
            name="program",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                null=True,
                blank=True,
                related_name="hits",
                to="competitions.shootingprogram",
            ),
        ),
        migrations.AddField(
            model_name="score",
            name="from_hits",
            field=models.BooleanField("aus Treffern berechnet", default=False),
        ),
        migrations.AlterField(
            model_name="hit",
            name="scoring",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name="hits",
                to="competitions.scoring",
            ),
        ),
        migrations.AddConstraint(
            model_name="hit",
            constraint=models.UniqueConstraint(
                fields=["program", "starter", "number"], name="competitions_durchgang_treffer_nr"
            ),
        ),
        migrations.RunPython(migrate_programs, migrations.RunPython.noop),
        migrations.RunPython(rls, undo_rls),
    ]
