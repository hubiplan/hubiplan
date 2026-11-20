"""Datenschutz-Werkzeuge: Einstellungen, eigene Verarbeitungstätigkeiten, Datenpannen.

Rückweg: Tabellen werden beim Zurücknehmen gelöscht (neue App, keine bestehenden Daten).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0074_hilfe_rueckmeldung"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PrivacySettings",
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
                    "dpo_name",
                    models.CharField(
                        blank=True,
                        max_length=200,
                        verbose_name="Datenschutzbeauftragte/r",
                    ),
                ),
                (
                    "dpo_contact",
                    models.CharField(
                        blank=True, max_length=300, verbose_name="Kontakt"
                    ),
                ),
                (
                    "hoster",
                    models.CharField(
                        blank=True,
                        max_length=300,
                        verbose_name="Betreiber der HUBIplan-Instanz",
                    ),
                ),
                (
                    "toms",
                    models.TextField(
                        blank=True,
                        verbose_name="Technische und organisatorische Maßnahmen",
                    ),
                ),
                ("hidden_keys", models.JSONField(blank=True, default=list)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ProcessingActivity",
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
                ("title", models.CharField(max_length=200, verbose_name="Bezeichnung")),
                ("purpose", models.TextField(blank=True, verbose_name="Zweck")),
                (
                    "legal_basis",
                    models.CharField(
                        blank=True, max_length=300, verbose_name="Rechtsgrundlage"
                    ),
                ),
                (
                    "subjects",
                    models.CharField(
                        blank=True, max_length=300, verbose_name="Betroffene"
                    ),
                ),
                (
                    "categories",
                    models.TextField(blank=True, verbose_name="Datenkategorien"),
                ),
                ("recipients", models.TextField(blank=True, verbose_name="Empfänger")),
                (
                    "third_country",
                    models.CharField(
                        blank=True,
                        max_length=300,
                        verbose_name="Übermittlung in Drittländer",
                    ),
                ),
                ("retention", models.TextField(blank=True, verbose_name="Löschfrist")),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                "ordering": ["title", "pk"],
            },
        ),
        migrations.CreateModel(
            name="DataBreach",
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
                    "title",
                    models.CharField(max_length=200, verbose_name="Kurzbezeichnung"),
                ),
                (
                    "discovered_at",
                    models.DateTimeField(verbose_name="Bekannt geworden"),
                ),
                (
                    "occurred",
                    models.CharField(
                        blank=True,
                        max_length=200,
                        verbose_name="Zeitpunkt oder Zeitraum der Panne",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True, max_length=5000, verbose_name="Was ist passiert?"
                    ),
                ),
                (
                    "categories",
                    models.TextField(
                        blank=True, max_length=2000, verbose_name="Betroffene Daten"
                    ),
                ),
                (
                    "affected",
                    models.CharField(
                        blank=True,
                        max_length=300,
                        verbose_name="Betroffene Personen (Art, ungefähre Zahl)",
                    ),
                ),
                (
                    "consequences",
                    models.TextField(
                        blank=True,
                        max_length=3000,
                        verbose_name="Wahrscheinliche Folgen",
                    ),
                ),
                (
                    "measures",
                    models.TextField(
                        blank=True, max_length=5000, verbose_name="Ergriffene Maßnahmen"
                    ),
                ),
                (
                    "risk",
                    models.CharField(
                        choices=[
                            ("unlikely", "voraussichtlich kein Risiko"),
                            ("risk", "Risiko"),
                            ("high", "hohes Risiko"),
                        ],
                        default="risk",
                        max_length=10,
                    ),
                ),
                (
                    "reported_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Gemeldet an die Aufsichtsbehörde",
                    ),
                ),
                (
                    "report_reference",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Aktenzeichen der Meldung",
                    ),
                ),
                (
                    "no_report_reason",
                    models.TextField(
                        blank=True, max_length=3000, verbose_name="Begründung"
                    ),
                ),
                (
                    "notified_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Betroffene benachrichtigt"
                    ),
                ),
                (
                    "closed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Abgeschlossen"
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-discovered_at", "-pk"],
                "indexes": [
                    models.Index(
                        fields=["organization", "closed_at"],
                        name="privacy_dat_organiz_4dc68f_idx",
                    )
                ],
            },
        ),
    ]
