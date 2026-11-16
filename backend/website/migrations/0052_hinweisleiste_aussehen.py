"""Hinweisleiste auffälliger (Ralf 16.11.2026): Stil, Platz, Symbol, Knopf und Countdown.
Nur neue Spalten mit Datenbank-Vorgabe; die vorige Fassung kann weiter Zeilen einfügen.
Abwärtsverträglich.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0051_db_default_rueckweg"),
    ]

    operations = [
        migrations.AddField(
            model_name="website",
            name="notice_style",
            field=models.CharField(
                choices=[
                    ("accent", "Akzentfarbe"),
                    ("alert", "Achtung"),
                    ("festive", "Festlich"),
                    ("quiet", "Schlicht in Kopffarbe"),
                ],
                db_default="accent",
                default="accent",
                max_length=10,
                verbose_name="Stil der Hinweisleiste",
            ),
        ),
        migrations.AddField(
            model_name="website",
            name="notice_place",
            field=models.CharField(
                choices=[
                    ("top", "über dem Kopf"),
                    ("below", "unter dem Kopf"),
                    ("float", "schwebend unten"),
                ],
                db_default="below",
                default="below",
                max_length=10,
                verbose_name="Platz der Hinweisleiste",
            ),
        ),
        migrations.AddField(
            model_name="website",
            name="notice_icon",
            field=models.CharField(
                choices=[
                    ("auto", "passend zum Stil"),
                    ("megaphone", "Lautsprecher"),
                    ("calendar", "Kalender"),
                    ("star", "Stern"),
                    ("info", "Info"),
                    ("alert", "Ausrufezeichen"),
                    ("none", "kein Symbol"),
                ],
                db_default="auto",
                default="auto",
                max_length=10,
                verbose_name="Symbol der Hinweisleiste",
            ),
        ),
        migrations.AddField(
            model_name="website",
            name="notice_button",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=40,
                verbose_name="Knopf der Hinweisleiste",
            ),
        ),
        migrations.AddField(
            model_name="website",
            name="notice_date",
            field=models.DateField(blank=True, null=True, verbose_name="Countdown bis"),
        ),
    ]
