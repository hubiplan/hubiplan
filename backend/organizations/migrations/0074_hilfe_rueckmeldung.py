"""Hilfe: „Hat das geholfen?“ und Suchwörter ohne Treffer (ohne Person und Einheit).

Zwei neue Tabellen; die vorige Fassung kennt sie nicht und braucht sie nicht.
Abwärtsverträglich; Rückweg entfernt die Tabellen.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0073_bilderspeicher_grenze"),
    ]

    operations = [
        migrations.CreateModel(
            name="HelpFeedback",
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
                ("key", models.CharField(max_length=80, verbose_name="Hilfetext")),
                ("language", models.CharField(max_length=5, verbose_name="Sprache")),
                (
                    "version",
                    models.CharField(blank=True, max_length=40, verbose_name="Fassung"),
                ),
                ("helpful", models.BooleanField(verbose_name="hat geholfen")),
                (
                    "comment",
                    models.CharField(blank=True, max_length=300, verbose_name="Was hat gefehlt?"),
                ),
                ("day", models.DateField(verbose_name="Tag")),
            ],
            options={
                "verbose_name": "Rückmeldung zur Hilfe",
                "verbose_name_plural": "Rückmeldungen zur Hilfe",
                "ordering": ["-day", "-id"],
                "indexes": [models.Index(fields=["key"], name="helpfeedback_key")],
            },
        ),
        migrations.CreateModel(
            name="HelpSearchMiss",
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
                ("term", models.CharField(max_length=60, verbose_name="Suchwörter")),
                ("language", models.CharField(max_length=5, verbose_name="Sprache")),
                ("count", models.PositiveIntegerField(default=1, verbose_name="Anzahl")),
                ("last_day", models.DateField(verbose_name="zuletzt am")),
            ],
            options={
                "verbose_name": "Suche in der Hilfe ohne Treffer",
                "verbose_name_plural": "Suchen in der Hilfe ohne Treffer",
                "ordering": ["-count", "term"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("term", "language"), name="helpsearchmiss_einmalig"
                    )
                ],
            },
        ),
    ]
