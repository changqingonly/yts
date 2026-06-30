from __future__ import annotations

import builtins

import pytest
from yts_server.eval.phoenix import init_phoenix


def test_phoenix_init_fails_when_enabled_but_dependency_missing(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "phoenix":
            raise ModuleNotFoundError("No module named 'phoenix'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ModuleNotFoundError, match="phoenix"):
        init_phoenix()
