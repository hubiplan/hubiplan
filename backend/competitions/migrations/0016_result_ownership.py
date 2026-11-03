from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("competitions", "0015_rls_urkunden"), ("peering", "0013_sammelaustritt")]
    operations = [
        migrations.AddField(
            model_name="starter",
            name="result_coupling",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="peering.coupling",
            ),
        )
    ]
