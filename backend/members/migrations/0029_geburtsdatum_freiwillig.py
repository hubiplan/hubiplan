from django.db import migrations


class Migration(migrations.Migration):
    """Geburtsdatum ist für Personen freiwillig. Abwärtsverträglich: nur eine
    Bedingung fällt weg, Spalten bleiben."""

    dependencies = [
        ("members", "0028_organisation_groesse"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="person",
            name="person_birth_date_required",
        ),
    ]
