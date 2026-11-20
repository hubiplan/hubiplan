import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Glückwünsche: Einstellung je Verein und Glückwünsche je Tag. Neue Tabellen, ältere Fassungen
    nutzen sie nicht. Rückweg: Migration zurücknehmen (Tabellen entfallen)."""

    initial = True

    dependencies = [
        ("circulars", "0019_glueckwunsch"),
        ("organizations", "0074_hilfe_rueckmeldung"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GreetingSettings",
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
                    "birthdays",
                    models.CharField(
                        choices=[
                            ("off", "keine"),
                            ("round", "nur zu besonderen Geburtstagen"),
                            ("all", "zu jedem Geburtstag"),
                        ],
                        default="off",
                        max_length=6,
                    ),
                ),
                (
                    "round_ages",
                    models.CharField(
                        blank=True,
                        default="18, 30, 40, 50, 60, 65, 70, 75",
                        max_length=200,
                    ),
                ),
                ("every_year_from", models.PositiveSmallIntegerField(default=80)),
                ("jubilees", models.BooleanField(default=False)),
                ("approval", models.BooleanField(default=False)),
                ("lead_days", models.PositiveSmallIntegerField(default=7)),
                ("send_hour", models.PositiveSmallIntegerField(default=9)),
                ("via_app", models.BooleanField(default=True)),
                ("also_mail", models.BooleanField(default=False)),
                (
                    "birthday_subject",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                (
                    "birthday_body",
                    models.TextField(blank=True, default="", max_length=5000),
                ),
                (
                    "jubilee_subject",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                (
                    "jubilee_body",
                    models.TextField(blank=True, default="", max_length=5000),
                ),
                ("reply_to", models.EmailField(blank=True, default="", max_length=254)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="greeting_settings",
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
            ],
            options={
                "verbose_name": "Einstellung für Glückwünsche",
            },
        ),
        migrations.CreateModel(
            name="GreetingBatch",
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
                ("date", models.DateField()),
                (
                    "kind",
                    models.CharField(
                        choices=[("birthday", "Geburtstag"), ("jubilee", "Jubiläum")],
                        max_length=10,
                    ),
                ),
                ("skipped_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "circular",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="greeting_batch",
                        to="circulars.circular",
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
                    "skipped_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["date", "kind"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "date", "kind"),
                        name="glueckwunsch_je_tag_und_anlass",
                    )
                ],
            },
        ),
    ]
