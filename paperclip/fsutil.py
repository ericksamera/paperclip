from __future__ import annotations

# Deprecated: use paperclip.util.rmtree_best_effort instead.
#
# Kept temporarily so any external imports fail loudly in review rather than at runtime,
# but our internal code should no longer import from here.

from .util import rmtree_best_effort

__all__ = ["rmtree_best_effort"]
