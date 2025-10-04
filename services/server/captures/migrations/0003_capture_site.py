from django.db import migrations, models
from urllib.parse import urlparse


def forwards_fill_site(apps, schema_editor):
    Capture = apps.get_model("captures", "Capture")
    for c in Capture.objects.all().only("id", "url"):
        host = ""
        try:
            host = (urlparse(c.url).hostname or "").replace("www.", "")
        except Exception:
            host = ""
        if host != c.__dict__.get("site", ""):
            c.site = host
            c.save(update_fields=["site"])


class Migration(migrations.Migration):
    dependencies = [("captures", "0002_collections")]
    operations = [
        migrations.AddField(
            model_name="capture",
            name="site",
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.RunPython(forwards_fill_site, reverse_code=migrations.RunPython.noop),
    ]
