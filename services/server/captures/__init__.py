# Make dotted lookups like "captures.artifacts" resolvable for tests/patch().
from . import artifacts  # noqa: F401

__all__ = ["artifacts"]
