"""modules/bar-workspaces: the manifest and the widget. The install, the one enable and
the undo are the shared mechanism's, pinned per plugin folder in
tests/test_plugins_contract.py."""

import json
import re
from pathlib import Path

PLUGIN = Path(__file__).parent / "plugin"
ID = "hyprconf.workspaces"


def test_manifest_declares_the_slot_and_entry_point_the_shell_reads() -> None:
    """No `barWidget.defaultSection` — the clonedFrom swap inherits the stock widget's slot — and none of the keys shell.qml:1400-1405 already defaults."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID and manifest["kinds"] == ["bar-widget"]
    assert manifest["entryPoints"] == {"barWidget": "Workspaces.qml"}
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.workspaces"
    assert manifest["barWidget"] == {"category": "Compositor"}


def test_the_widget_lists_live_workspaces_and_keeps_the_stock_ipc_target():
    """Why this widget replaces the stock one, and what it must not break: the ids come from
    Hyprland, never a fixed 1-5 list or an id cap the way stock does, and `moduleName` stays
    the built-in id, which is the stable IPC target the clonedFrom swap hands over."""
    code = re.sub(r"//.*", "", (PLUGIN / "Workspaces.qml").read_text())  # comments off
    assert 'moduleName: "omarchy.workspaces"' in code
    assert "Hyprland.workspaces.values" in code
    assert not re.search(r"\[\s*1\s*,\s*2\b", code), "a fixed pill list"
    assert not re.search(r"[<>]=?\s*[1-9]\d*", code), "an id cap (`id > 0` is the only bound)"
