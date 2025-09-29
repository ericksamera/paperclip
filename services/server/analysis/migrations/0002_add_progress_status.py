from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("analysis", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="analysisrun",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[("PENDING","PENDING"),("RUNNING","RUNNING"),("SUCCESS","SUCCESS"),("FAILED","FAILED")],
                default="PENDING",
            ),
        ),
        migrations.AddField(
            model_name="analysisrun",
            name="progress",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
