import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.encfields
from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("music", "0013_equipment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="PayoutRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("reference", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
                ("execution_date", models.DateField()),
                ("debtor", core.encfields.EncryptedJSONField(default=dict, strict=True)),
                ("cancelled_at", models.DateTimeField(null=True, blank=True)),
                ("exported_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        "organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    "bank_account",
                    models.ForeignKey(
                        "finance.account", on_delete=django.db.models.deletion.PROTECT
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
        migrations.CreateModel(
            name="PayoutItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("amount", models.DecimalField(max_digits=12, decimal_places=2)),
                ("payee", core.encfields.EncryptedJSONField(default=dict, strict=True)),
                ("released", models.BooleanField(default=False)),
                (
                    "organization",
                    models.ForeignKey(
                        "organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        "music.payoutrun",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                    ),
                ),
                (
                    "claim",
                    models.ForeignKey(
                        "music.musicianclaim",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payout_items",
                    ),
                ),
                (
                    "expense",
                    models.OneToOneField(
                        "music.performanceexpense",
                        null=True,
                        blank=True,
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=["claim"],
                        condition=models.Q(released=False),
                        name="music_claim_one_payout",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(amount__gt=0), name="music_payout_positive"
                    ),
                ]
            },
        ),
        *[
            migrations.RunSQL(enable_rls_sql(table), disable_rls_sql(table))
            for table in ["music_payoutrun", "music_payoutitem"]
        ],
    ]
