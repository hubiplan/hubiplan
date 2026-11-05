import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.encfields
from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0014_payout_runs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="guestaccess",
            name="score_shares",
            field=core.encfields.EncryptedJSONField(default=list, db_default=[], strict=True),
        ),
        migrations.CreateModel(
            name="RehearsalGuestAccess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("original_start", models.DateTimeField()),
                ("nonce", models.UUIDField(default=uuid.uuid4)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(null=True, blank=True)),
                ("score_shares", core.encfields.EncryptedJSONField(default=list, strict=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        "organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    "invitation",
                    models.ForeignKey(
                        "music.rehearsalinvitation",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_accesses",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        settings.AUTH_USER_MODEL,
                        null=True,
                        blank=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=["invitation", "original_start"], name="music_guest_rehearsal_once"
                    )
                ]
            },
        ),
        migrations.RunSQL(
            enable_rls_sql("music_rehearsalguestaccess"),
            disable_rls_sql("music_rehearsalguestaccess"),
        ),
    ]
