"""Designpakete (Ralf 2026-11-02): eingespielte Designs je Installation, Freigabe je Webseite.

Website.design verliert die festen choices (auch Paket-Schlüssel), bleibt aber ein Textfeld
mit denselben Werten; ältere Fassungen lesen es weiter (abwärtsverträglich).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0030_zeitleiste_mehrere_bilder"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="website",
            name="design",
            field=models.CharField(default="classic", max_length=40, verbose_name="Design"),
        ),
        migrations.CreateModel(
            name="DesignPackage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=40, unique=True, verbose_name="Kürzel")),
                ("label", models.CharField(max_length=60, verbose_name="Name")),
                ("label_en", models.CharField(blank=True, max_length=60, verbose_name="Name (Englisch)")),
                ("hint", models.CharField(blank=True, max_length=300, verbose_name="Beschreibung")),
                ("hint_en", models.CharField(blank=True, max_length=300, verbose_name="Beschreibung (Englisch)")),
                ("roles", models.JSONField(default=dict, verbose_name="Farbrollen")),
                ("sketch_like", models.CharField(default="classic", max_length=20, verbose_name="Skizze wie")),
                ("css", models.TextField(blank=True, verbose_name="Gestaltung (CSS)")),
                ("templates", models.JSONField(blank=True, default=dict, verbose_name="Vorlagen")),
                ("content_hash", models.CharField(max_length=64, verbose_name="Prüfsumme")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
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
                    "websites",
                    models.ManyToManyField(
                        blank=True,
                        related_name="design_packages",
                        to="website.website",
                        verbose_name="freigegeben für",
                    ),
                ),
            ],
            options={
                "verbose_name": "Designpaket",
                "verbose_name_plural": "Designpakete",
                "ordering": ["label", "key"],
            },
        ),
    ]
