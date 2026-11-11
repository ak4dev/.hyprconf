"""modules/bar-workspaces: the manifest and the widget. The install, the one enable and
the undo are the shared mechanism's, pinned per plugin folder in
tests/test_plugins_contract.py."""

import json
import re
from pathlib import Path

import pytest

from conftest import NEEDS_OMARCHY, OMARCHY

PLUGIN = Path(__file__).parent / "plugin"
ID = "hyprconf.workspaces"
STOCK_WIDGET = OMARCHY / "shell/plugins/bar/widgets/Workspaces.qml"
# What the widget keeps of the stock one, verbatim: from the root's opening line down to
# the block the stock file continues with.
KEPT = r"^BarWidget \{$.*?^  Connections \{$.*?^  \}$"


def code(path: Path) -> str:
    return re.sub(r"//.*", "", path.read_text())  # comments off


def test_manifest_declares_the_slot_and_entry_point_the_shell_reads() -> None:
    """No `barWidget.defaultSection` — the clonedFrom swap inherits the stock widget's slot — and none of the keys shell.qml:1464-1470 already defaults."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID and manifest["kinds"] == ["bar-widget"]
    assert manifest["entryPoints"] == {"barWidget": "Workspaces.qml"}
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.workspaces"
    assert manifest["barWidget"] == {"category": "Compositor"}


def test_the_widget_lists_live_workspaces_by_their_monitors_own_slot() -> None:
    """Why this widget replaces the stock one, and what it must not break: the ids come from
    Hyprland, never stock's fixed first five, each bar lists its own monitor's block under
    the slot numbers Omarchy's keys use, and a click goes through Omarchy's own
    o.workspaces.focus — a bare id would land on another monitor's block."""
    qml = code(PLUGIN / "Workspaces.qml")
    assert 'moduleName: "omarchy.workspaces"' in qml
    assert "Hyprland.workspaces.values" in qml
    assert not re.search(r"base \+ \d", qml), "a fixed pill list"
    assert "String(root.slotOf(modelData))" in qml
    assert "root.activeWorkspaceId() === modelData" in qml, "the mark follows this bar's monitor"
    assert '"o.workspaces.focus(" + root.slotOf(id)' in qml


@pytest.mark.skipif(not STOCK_WIDGET.is_file(), reason=NEEDS_OMARCHY)
def test_the_per_monitor_logic_is_omarchys_own() -> None:
    """Which monitor, which block of ten, the click and the refresh are the stock widget's,
    comment for comment, but for the list of ids and what stock adds for its layout glyph —
    red on a release that changes how workspaces map to monitors, which is the signal to
    take the stock lines again (the widget's header names them)."""
    ours = re.search(KEPT, (PLUGIN / "Workspaces.qml").read_text(), re.M | re.S)
    assert ours, "the kept block was not found"
    kept = [ln for ln in ours.group(0).splitlines() if ln.strip()]
    theirs = [ln for ln in STOCK_WIDGET.read_text().splitlines() if ln.strip()]
    missing = [ln for ln in kept if ln not in theirs]
    assert missing == [
        "  // The monitor's own that exist, ascending. After them come workspaces that",
        "  // are only visiting: those of a monitor that is unplugged, which had no room",
        "  // to join this one's. id < 0 is a special workspace (scratchpad) and is",
        "  // never listed, as in stock.",
        "    var ids = []",
    ]
    # In stock's order too — `in` on an iterator consumes it up to the match.
    rest = iter(theirs)
    assert all(ln in rest for ln in kept if ln not in missing), "a kept line was moved"
