"""The desktop half is told, live, when the record changes and when an act-then-notify action can be undone."""
import sys
import types

import tenure as core


def test_push_sends_a_namespaced_plugin_event(monkeypatch):
    sent = []
    fake = types.ModuleType("hermes_cli.plugin_events")
    fake.broadcast_plugin_event = lambda pid, ev, payload=None: sent.append((pid, ev, payload))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugin_events", fake)
    core._push("acted", {"undo_id": 3})
    assert sent == [("tenure", "acted", {"undo_id": 3})]


def test_push_never_raises_without_a_gateway(monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_cli.plugin_events", None)      # import fails
    core._push("changed")


def test_profile_name(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "_hermes_home", lambda: str(tmp_path / "profiles" / "ops"))
    assert core._profile_name() == "ops"
    monkeypatch.setattr(core, "_hermes_home", lambda: str(tmp_path / ".hermes"))
    assert core._profile_name() == "default"
