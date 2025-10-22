# services/server/captures/migrations/0004_doi_norm.py
from django.db import migrations, models


def _norm(doi: str | None) -> str | None:
    if not doi:
        return None
    d = str(doi).strip()
    # very light normalization (keep in-migration, don't import app code)
    lowers = d.lower()
    for p in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if lowers.startswith(p):
            d = d[len(p) :]
            break
    d = d.strip().strip("/")
    return d.lower() or None


def forwards(apps, schema_editor):
    Capture = apps.get_model("captures", "Capture")
    Reference = apps.get_model("captures", "Reference")

    # Backfill Capture.doi_norm
    for c in Capture.objects.all().only("id", "doi", "meta"):
        candidate = c.doi or (
            (c.meta or {}).get("doi") if isinstance(c.meta, dict) else ""
        )
        nd = _norm(candidate)
        if nd != getattr(c, "doi_norm", None):
            c.doi_norm = nd
            c.save(update_fields=["doi_norm"])

    # Backfill Reference.doi_norm
    for r in Reference.objects.all().only("id", "doi"):
        nd = _norm(r.doi)
        if nd != getattr(r, "doi_norm", None):
            r.doi_norm = nd
            r.save(update_fields=["doi_norm"])


class Migration(migrations.Migration):
    dependencies = [
        ("captures", "0003_capture_site"),
    ]

    operations = [
        migrations.AddField(
            model_name="capture",
            name="doi_norm",
            field=models.CharField(
                max_length=255, null=True, blank=True, db_index=True
            ),
        ),
        migrations.AddField(
            model_name="reference",
            name="doi_norm",
            field=models.CharField(
                max_length=255, null=True, blank=True, db_index=True
            ),
        ),
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="reference",
            unique_together={("capture", "doi_norm")},
        ),
    ]
