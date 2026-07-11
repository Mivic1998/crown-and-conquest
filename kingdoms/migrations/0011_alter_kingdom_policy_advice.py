from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kingdoms", "0010_remove_kingdom_policy_advice_exists_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            """
            UPDATE kingdoms_kingdom
            SET policy_advice = '{}';
            """
        ),

        migrations.AlterField(
            model_name="kingdom",
            name="policy_advice",
            field=models.JSONField(
                blank=True,
                default=dict,
            ),
        ),
    ]