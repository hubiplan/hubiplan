import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0018_kapelle_seite"),
        ("organizations", "0062_umsatzsteuer"),
    ]
    operations = [
        migrations.AddField(
            model_name="scoredocument",
            name="position",
            field=models.PositiveSmallIntegerField(db_default=0, default=0),
        ),
        migrations.CreateModel(
            name="ScoreFolder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("marchbook", "marchbook"),
                            ("repertoire", "repertoire"),
                            ("other", "other"),
                        ],
                        default="other",
                        max_length=12,
                    ),
                ),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("note", models.CharField(blank=True, max_length=1000)),
                ("active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"ordering": ["position", "name", "pk"]},
        ),
        migrations.CreateModel(
            name="ScoreFolderUnit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.department",
                    ),
                ),
                (
                    "folder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="units",
                        to="music.scorefolder",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("folder", "department"), name="notenmappe_einheit_einmal"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ScoreFolderItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("position", models.PositiveIntegerField(default=1)),
                ("number", models.CharField(blank=True, max_length=20)),
                (
                    "arrangement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="music.arrangement",
                    ),
                ),
                (
                    "folder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="music.scorefolder",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["position", "pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("folder", "arrangement"), name="notenmappe_stueck_einmal"
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("number", ""), _negated=True),
                        fields=("folder", "number"),
                        name="notenmappe_nummer_einmal",
                    ),
                ],
            },
        ),
        migrations.RunSQL(
            enable_rls_sql("music_scorefolder"), disable_rls_sql("music_scorefolder")
        ),
        migrations.RunSQL(
            enable_rls_sql("music_scorefolderunit"), disable_rls_sql("music_scorefolderunit")
        ),
        migrations.RunSQL(
            enable_rls_sql("music_scorefolderitem"), disable_rls_sql("music_scorefolderitem")
        ),
    ]
