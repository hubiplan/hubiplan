from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0034_datenschluesselwechsel")]

    operations = [
        migrations.AddField(
            model_name="datakey",
            name="retired_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="datakey",
            name="retirement_reference",
            field=models.CharField(max_length=100, default="", db_default=""),
        ),
        migrations.AddField(
            model_name="datakey",
            name="retirement_checksum",
            field=models.CharField(max_length=64, default="", db_default=""),
        ),
        migrations.AddConstraint(
            model_name="datakey",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        retired_at__isnull=True, retirement_reference="", retirement_checksum=""
                    )
                    | (
                        models.Q(retired_at__isnull=False, is_active=False, wrapped="")
                        & ~models.Q(retirement_reference="")
                        & ~models.Q(retirement_checksum="")
                    )
                ),
                name="core_datakey_ausmusterung",
            ),
        ),
        migrations.RunSQL(
            sql=migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM core_datakey WHERE retired_at IS NOT NULL) THEN
                        RAISE EXCEPTION 'Ausmusterungsnachweise erhalten; Rückmigration nicht möglich.';
                    END IF;
                END $$;
            """,
        ),
    ]
