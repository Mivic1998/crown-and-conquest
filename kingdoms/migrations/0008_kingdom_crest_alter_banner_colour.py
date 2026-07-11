# Generated for premium royal identity options.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kingdoms", "0007_turnhistory_agriculture_investment_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="kingdom",
            name="banner_colour",
            field=models.CharField(
                choices=[
                    ("blue", "Royal Blue"),
                    ("crimson", "Crimson Empire"),
                    ("emerald", "Emerald Realm"),
                    ("purple", "Imperial Purple"),
                    ("golden", "Golden Kingdom"),
                ],
                default="blue",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="kingdom",
            name="crest",
            field=models.CharField(
                choices=[
                    ("standard", "Standard Crown"),
                    ("lion", "Crimson Lion"),
                    ("dragon", "Emerald Dragon"),
                    ("stag", "Imperial Stag"),
                    ("eagle", "Black Eagle"),
                    ("wolf", "Ice Wolf"),
                ],
                default="standard",
                max_length=20,
            ),
        ),
    ]
