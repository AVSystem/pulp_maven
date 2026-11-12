from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maven", "0016_mavenpendingdeploy"),
    ]

    operations = [
        migrations.AddField(
            model_name="mavenpendingdeploy",
            name="pull_through",
            field=models.BooleanField(default=False),
        ),
    ]
