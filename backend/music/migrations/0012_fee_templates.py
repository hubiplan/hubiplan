import django.db.models.deletion
from django.db import migrations, models

from core.rls import disable_rls_sql, enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [("music", "0011_guest_access")]
    operations = [
        migrations.CreateModel(
            name="FeeTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=150)),
                ("fee", models.DecimalField(max_digits=12, decimal_places=2, default=0)),
                ("allowance", models.DecimalField(max_digits=12, decimal_places=2, default=0)),
                ("active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        to="organizations.organization", on_delete=django.db.models.deletion.CASCADE
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(fee__gte=0, allowance__gte=0),
                        name="music_fee_template_nonnegative",
                    )
                ]
            },
        ),
        migrations.RunSQL(
            enable_rls_sql("music_feetemplate"), disable_rls_sql("music_feetemplate")
        ),
    ]
