import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Buchung für ein Mitglied (nullbar, abwärtsverträglich)."""

    dependencies = [
        ("bookings", "0002_ausleihe"),
        ("members", "0036_hinweis_volljaehrigkeit"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="members.membership",
            ),
        ),
    ]
