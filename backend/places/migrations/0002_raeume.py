"""Räume in Orten: Gebäude mit Anschrift, darunter Räume (nur das Schema).

Das Zusammenführen bestehender Orte steht in 0003_raeume_zusammenfuehren, in einer eigenen
Transaktion: PostgreSQL legt die Indizes dieser Migration erst am Ende an und verweigert das,
solange geänderte Zeilen offene Fremdschlüsselprüfungen haben („pending trigger events“).
"""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("places", "0001_orte"),
    ]

    operations = [
        migrations.AddField(
            model_name="place",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rooms",
                to="places.place",
                verbose_name="Gebäude",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="place",
            name="ort_name_je_org",
        ),
        migrations.AddConstraint(
            model_name="place",
            constraint=models.UniqueConstraint(
                condition=Q(parent__isnull=True),
                fields=("organization", "name"),
                name="ort_name_je_org",
            ),
        ),
        migrations.AddConstraint(
            model_name="place",
            constraint=models.UniqueConstraint(
                condition=Q(parent__isnull=False),
                fields=("parent", "name"),
                name="raum_name_je_ort",
            ),
        ),
    ]
