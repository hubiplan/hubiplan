# Issue #723: Rücksprungadresse für Meta über die Vereinsadresse der Einheit.
# Bereits verbundene Kanäle behalten die bisherige Adresse der Instanz, die in ihrer Meta-App
# eingetragen ist. Neue Kanäle nutzen die Vereinsadresse ihrer Einheit.

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def pin_existing(apps, schema_editor):
    SocialFeed = apps.get_model("website", "SocialFeed")
    base = (
        getattr(settings, "SOCIAL_CALLBACK_BASE", "") or getattr(settings, "FRONTEND_URL", "")
    ).rstrip("/")
    if base:
        SocialFeed.objects.filter(Q(connected_at__isnull=False) | ~Q(access_token="")).update(
            redirect_base=base[:300]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0055_namensform_je_bereich"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialfeed",
            name="redirect_base",
            field=models.CharField(
                blank=True, db_default="", max_length=300, verbose_name="Rücksprungadresse"
            ),
        ),
        migrations.RunPython(pin_existing, migrations.RunPython.noop),
    ]
