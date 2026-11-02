import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("oidc", "0004_nur_rollen"),
        ("organizations", "__latest__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="manage_accounts",
            field=models.BooleanField(default=False, verbose_name="Konten automatisch deaktivieren"),
        ),
        migrations.AddField(
            model_name="client",
            name="service_user",
            field=models.CharField(
                blank=True, default="", max_length=64, verbose_name="Dienstkonto"
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="service_password",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="client",
            name="account_group",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Gruppe der Konten über HUBIplan",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="sync_error",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="client",
            name="synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="Account",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "nc_user",
                    models.CharField(max_length=64, verbose_name="Benutzername in der Nextcloud"),
                ),
                ("first_login_at", models.DateTimeField(auto_now_add=True)),
                ("last_login_at", models.DateTimeField()),
                ("disabled_by_hubiplan", models.BooleanField(default=False)),
                ("changed_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.CharField(blank=True, default="", max_length=300)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accounts",
                        to="oidc.client",
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
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Nextcloud-Konto",
                "verbose_name_plural": "Nextcloud-Konten",
                "ordering": ["nc_user"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("client", "user"), name="oidc_account_unique_user"
                    )
                ],
            },
        ),
        migrations.RunSQL(enable_rls_sql("oidc_account"), disable_rls_sql("oidc_account")),
    ]
