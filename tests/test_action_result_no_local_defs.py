from __future__ import annotations

import inspect

import paperclip.services.captures_service as captures_service
import paperclip.services.collections_service as collections_service


def _module_source(mod) -> str:
    return inspect.getsource(mod)


def test_services_do_not_define_local_actionresult():
    # A blunt guardrail: local dataclass reintroductions are drift risks.
    for mod in (captures_service, collections_service):
        src = _module_source(mod)
        assert "class ActionResult" not in src
