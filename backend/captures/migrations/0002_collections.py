from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("captures", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Collection",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("name", models.CharField(max_length=200)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="captures.collection",
                    ),
                ),
            ],
            options={"ordering": ["name"], "unique_together": {("parent", "name")}},
        ),
        migrations.AddField(
            model_name="collection",
            name="captures",
            field=models.ManyToManyField(
                blank=True, related_name="collections", to="captures.capture"
            ),
        ),
    ]
