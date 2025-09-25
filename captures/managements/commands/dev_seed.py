from __future__ import annotations
from django.core.management.base import BaseCommand
from captures.models import Capture, Reference
from paperclip.artifacts import write_text_artifact, write_json_artifact

class Command(BaseCommand):
    help = "Create a sample Capture with a couple of references and artifacts."

    def handle(self, *args, **kwargs):
        cap = Capture.objects.create(
            url="https://example.org/demo-paper",
            title="Demo Paperclip Capture",
            doi="10.1234/demo.0001",
            year="2024",
            meta={"container_title": "Example Journal", "authors": [{"family":"Smith","given":"Jane"}]},
            csl={"title":"Demo Paperclip Capture","abstract":"This is a demo abstract."},
        )
        Reference.objects.create(
            capture=cap,
            ref_id="ref-1",
            raw="Smith, J. (2023). Interesting Things. Example Journal.",
            title="Interesting Things",
            doi="10.5555/ref.1",
            issued_year="2023",
            container_title="Example Journal",
            authors=[{"family":"Smith","given":"Jane"}],
        )
        Reference.objects.create(
            capture=cap,
            ref_id="ref-2",
            raw="Lee, A., & Chen, B. (2022). More Interesting Things.",
            title="More Interesting Things",
            issued_year="2022",
            container_title="Another Journal",
            authors=[{"family":"Lee","given":"Alex"},{"family":"Chen","given":"Bo"}],
        )

        # Minimal artifacts so detail page shows content
        html = "<h1>Demo Content</h1><p>Hello from Paperclip.</p>"
        write_text_artifact(str(cap.id), "content.html", html)
        write_text_artifact(str(cap.id), "page.html", f"<!doctype html><html><body>{html}</body></html>")
        write_json_artifact(str(cap.id), "raw_ingest.json", {"demo": True})
        write_json_artifact(str(cap.id), "parsed.json", {"metadata": cap.meta, "references": []})
        write_json_artifact(str(cap.id), "server_output_reduced.json", {"metadata": cap.meta, "body": []})
        write_json_artifact(str(cap.id), "server_parsed.json", {"id": str(cap.id), "title": cap.title})

        self.stdout.write(self.style.SUCCESS(f"Seeded demo capture {cap.id}"))
