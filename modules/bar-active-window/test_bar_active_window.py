"""modules/bar-active-window: the manifest, the widget, and the one thing its undo does
that no sibling's does — take back a slot the enable added. The install, the one enable
and the rest of the undo are the shared mechanism's, pinned per plugin folder in
tests/test_plugins_contract.py."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from conftest import Box, bar_shell

INSTALL, PLUGIN = Path(__file__).parent / "install", Path(__file__).parent / "plugin"
ID = "hyprconf.active-window"
STOCK = "omarchy.active-window"
MARKER = ".local/state/hyprconf/active-window-applied"


def listing(rows: list[dict] | None) -> str:
    """omarchy-plugin-list --json, with the `.enabled` the install reads (shell.qml:1681-1682);
    None is no shell answering, which exits 1 (bin/omarchy-shell:14-17)."""
    return "exit 1\n" if rows is None else f"printf %s {shlex.quote(json.dumps(rows))}\n"


@pytest.mark.parametrize(
    ("listed", "at_undo", "disabled"),
    [
        # Omarchy's default bar carries no omarchy.active-window, so the enable ADDED a slot
        # (PluginRegistry.qml:535-540) and undo takes it off again — a stock bar came back.
        ([{"id": ID, "enabled": False}], [{"id": ID}], [ID, STOCK]),
        # the stock widget was on the bar: the enable took ITS slot (:529-534) and the
        # disable hands that slot straight back (:555 -> :459-463).
        ([{"id": STOCK, "enabled": True}], [{"id": ID}], [ID]),
        # the copy already held a slot before this run
        ([{"id": ID, "enabled": True}], [{"id": ID}], [ID]),
        # the enable added a slot, but the user has put the stock title back by hand since:
        # our disable then moves nothing (:449-450) and theirs is not ours to splice off
        ([{"id": ID, "enabled": False}], [{"id": STOCK}], [ID]),
        # the list never answered, so whether the slot was added is unknown: stock stays
        (None, [{"id": ID}], [ID]),
    ],
)
def test_undo_takes_a_stock_widget_off_only_where_the_enable_added_the_slot(
    box: Box, listed: list[dict] | None, at_undo: list[dict], disabled: list[str]
) -> None:
    """Omarchy's default bar has no title widget, so leaving one behind is not stock
    (rule 5); one the user has placed themselves is not ours to take off either."""
    bar_shell(box, layout=[])
    box.stub("omarchy-plugin-list", listing(listed))
    assert box.run(INSTALL).returncode == 0
    bar_shell(box, layout=at_undo)  # the bar as it stands when the undo runs
    box.reset()
    assert box.undo("bar-active-window").returncode == 0
    assert [c[1] for c in box.calls_of("omarchy-plugin-disable")] == disabled
    assert not (box.home / MARKER).exists()


def test_the_manifest_is_the_clone_contract() -> None:
    # clonedFrom takes the stock widget's slot (PluginRegistry.qml:529-534); with no stock
    # entry in the bar, defaultSection left lands it after omarchy.workspaces (:270-275).
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["schemaVersion"] == 1 and manifest["kinds"] == ["bar-widget"]
    assert manifest["id"] == ID and manifest["entryPoints"] == {"barWidget": "ActiveWindow.qml"}
    assert manifest["omarchy"] == {"clonedFrom": STOCK}
    assert manifest["barWidget"] == {"category": "Compositor", "defaultSection": "left"}


def test_the_widget_keeps_the_stock_widget_s_behaviour() -> None:
    qml = (PLUGIN / "ActiveWindow.qml").read_text()
    # "Everything else is the stock widget's behaviour ... the stock IPC target keeps
    # working" (README): the built-in moduleName, both clicks (the two identical stock
    # close branches merged into one ||), the tooltip, and the title on two lines.
    assert 'moduleName: "omarchy.active-window"' in qml
    assert "mouse.button === Qt.MiddleButton || mouse.button === Qt.RightButton" in qml
    assert "root.toplevel.close()" in qml and "root.toplevel.activate()" in qml
    assert "bar.showTooltip(root, root.title)" in qml and "bar.hideTooltip(root)" in qml
    assert "maximumLineCount: 2" in qml
