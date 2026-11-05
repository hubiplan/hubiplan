import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.encfields
import core.privatefiles
import exchange.models
import music.models
from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0015_rehearsal_guests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="EngagementDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("reference", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
                ("kind", models.CharField(max_length=12)),
                ("status", models.CharField(max_length=12, default="issued")),
                ("snapshot", core.encfields.EncryptedJSONField(default=dict, strict=True)),
                (
                    "file",
                    core.privatefiles.PrivateFileField(
                        storage=exchange.models.private_storage,
                        upload_to=music.models.engagement_path,
                        blank=True,
                    ),
                ),
                ("sha256", models.CharField(max_length=64, blank=True)),
                ("valid_until", models.DateField(null=True, blank=True)),
                ("accepted_at", models.DateTimeField(null=True, blank=True)),
                (
                    "resolution_note",
                    core.encfields.EncryptedCharField(max_length=1000, strict=True, blank=True),
                ),
                (
                    "acceptance_note",
                    core.encfields.EncryptedCharField(max_length=1000, strict=True, blank=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        "organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    "performance",
                    models.ForeignKey(
                        "music.performance",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="engagement_documents",
                    ),
                ),
                (
                    "offer",
                    models.ForeignKey(
                        "music.engagementdocument",
                        on_delete=django.db.models.deletion.PROTECT,
                        null=True,
                        blank=True,
                        related_name="confirmations",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                    ),
                ),
            ],
        ),
        migrations.RunSQL(
            enable_rls_sql("music_engagementdocument"), disable_rls_sql("music_engagementdocument")
        ),
    ]
