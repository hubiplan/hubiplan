# Fachfrage FQ26 (Audit 02.11.): PKCE (S256) je Client verpflichtend

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("oidc", "0006_gruppen_fuer_rollen"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="require_pkce",
            field=models.BooleanField(default=True, verbose_name="nur mit PKCE (S256)"),
        ),
    ]
