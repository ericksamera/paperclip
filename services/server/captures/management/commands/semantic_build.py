from __future__ import annotations

from django.core.management.base import BaseCommand

from captures.semantic import build_index


class Command(BaseCommand):
    help = "Build/update semantic ANN index (Sentence Transformers)."

    def handle(self, *args, **opts):
        n, model = build_index()
        self.stdout.write(self.style.SUCCESS(f"Indexed {n} docs with model {model}"))
