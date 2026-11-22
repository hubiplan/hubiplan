from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0075_bankanbindung"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="menu_layout",
            field=models.JSONField(blank=True, null=True, verbose_name="Anordnung des Menüs"),
        ),
        migrations.AddField(
            model_name="organization",
            name="menu_layout_history",
            field=models.JSONField(
                blank=True,
                db_default=[],
                default=list,
                verbose_name="Frühere Anordnungen des Menüs",
            ),
        ),
    ]
