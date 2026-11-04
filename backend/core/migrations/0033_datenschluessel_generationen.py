import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0032_datenschluessel")]

    operations = [
        migrations.AddField(
            model_name="datakey",
            name="is_active",
            field=models.BooleanField(db_default=True, default=True),
        ),
        # Die neue Eindeutigkeit steht schon vor dem Entfernen der alten bereit.
        migrations.AddConstraint(
            model_name="datakey",
            constraint=models.UniqueConstraint(
                fields=("organization",),
                condition=models.Q(is_active=True),
                name="core_datakey_ein_aktiver",
            ),
        ),
        migrations.AlterField(
            model_name="datakey",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="organizations.organization",
            ),
        ),
        migrations.RunSQL(
            sql=migrations.RunSQL.noop,
            reverse_sql="""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM core_datakey WHERE NOT is_active)
                       OR EXISTS (SELECT 1 FROM core_datakey GROUP BY organization_id
                                  HAVING COUNT(*) > 1) THEN
                        RAISE EXCEPTION 'Mehrere oder inaktive Datenschlüssel: '
                            'Generationen erhalten; Rückmigration nicht möglich.';
                    END IF;
                END $$;
            """,
        ),
    ]
