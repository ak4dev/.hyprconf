"""modules/bar-active-window: the link, the one enable, the undo, the widget."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

INSTALL, PLUGIN = Path(__file__).parent / "install", Path(__file__).parent / "plugin"
ID = "hyprconf.active-window"
LINK, MARKER = f".config/omarchy/plugins/{ID}", ".local/state/hyprconf/active-window-applied"
LIST_KNOWS_IT = f'printf \'[{{"id": "{ID}"}}]\\n\'\n'  # the discovery wait (bin/omarchy-plugin-add:164-171) breaks at once


def _tree(home: Path) -> dict:
    return {  # mode, mtime and link target of everything under HOME; rglob never follows a link
        str(p): (p.lstat().st_mode, p.lstat().st_mtime_ns, p.is_symlink() and p.readlink())
        for p in home.rglob("*")
    }


def test_install_links_the_folder_and_enables_it_once(box) -> None:
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    assert (box.home / LINK).readlink() == PLUGIN and (box.home / LINK / "manifest.json").is_file()
    assert "omarchy-shell shell rescanPlugins" in box.calls
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    assert not any("--section" in c or c.startswith("omarchy-bar") for c in box.calls)
    assert (box.home / MARKER).exists()


def test_a_second_run_writes_nothing_and_enables_nothing(box) -> None:
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert box.run(INSTALL).returncode == 0
    before = _tree(box.home)
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert _tree(box.home) == before
    assert box.commands == ["omarchy-shell"]  # the rescan, and no mutating command at all


def test_a_real_folder_where_the_link_goes_is_moved_aside_once(box) -> None:
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    plugins = (box.home / LINK).parent
    (box.home / LINK).mkdir(parents=True)
    (box.home / LINK / "ActiveWindow.qml").write_text("// the copy from before\n")
    assert box.run(INSTALL).returncode == 0 and (box.home / LINK).is_symlink()
    backups = sorted(plugins.glob(f".{ID}.bak.*"))
    assert len(backups) == 1 and (backups[0] / "ActiveWindow.qml").is_file()
    assert box.run(INSTALL).returncode == 0 and sorted(plugins.glob(f".{ID}.bak.*")) == backups


def test_an_omarchy_plugin_add_checkout_is_left_to_omarchy(box) -> None:
    (box.home / LINK / ".git").mkdir(parents=True)
    proc = box.run(INSTALL)
    assert proc.returncode == 0 and "omarchy plugin update" in proc.stdout
    assert not (box.home / LINK).is_symlink()
    assert box.commands == [] and not (box.home / MARKER).exists()


def test_no_shell_answering_leaves_the_enable_for_the_next_run(box) -> None:
    box.stub("omarchy-plugin-list", "exit 1\n")
    box.stub("omarchy-plugin-enable", "exit 1\n")
    proc = box.run(INSTALL)
    assert proc.returncode == 0 and "next run" in proc.stdout
    assert (box.home / LINK).is_symlink() and not (box.home / MARKER).exists()
    assert box.commands.count("omarchy-plugin-list") == 1
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT), box.stub("omarchy-plugin-enable")
    assert box.run(INSTALL).returncode == 0 and (box.home / MARKER).exists()


def test_undo_disables_it_and_takes_the_link_and_marker_away(box) -> None:
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert box.run(INSTALL).returncode == 0
    proc = box.undo("bar-active-window")
    assert proc.returncode == 0, proc.stderr
    assert {f"omarchy-plugin-disable {ID}", "omarchy-shell shell rescanPlugins"} <= set(box.calls)
    assert not (box.home / LINK).is_symlink() and (PLUGIN / "manifest.json").is_file()
    assert not (box.home / MARKER).exists()


def test_undo_leaves_a_folder_that_is_not_its_own_link_whole(box) -> None:
    (box.home / LINK).mkdir(parents=True)
    (box.home / LINK / "ActiveWindow.qml").write_text("// not ours\n")
    assert box.undo("bar-active-window").returncode == 0
    assert (box.home / LINK / "ActiveWindow.qml").read_text() == "// not ours\n"


def test_the_manifest_is_the_clone_contract() -> None:
    # clonedFrom takes the stock widget's slot (PluginRegistry.qml:529-534); with no stock
    # entry in the bar, defaultSection left lands it after omarchy.workspaces (:270-275).
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["schemaVersion"] == 1 and manifest["kinds"] == ["bar-widget"]
    assert manifest["id"] == ID and manifest["entryPoints"] == {"barWidget": "ActiveWindow.qml"}
    assert manifest["omarchy"] == {"clonedFrom": "omarchy.active-window"}
    assert manifest["barWidget"] == {"category": "Compositor", "defaultSection": "left"}


def test_the_widget_qml_parses_and_keeps_the_stock_widget_s_behaviour() -> None:
    qml = (PLUGIN / "ActiveWindow.qml").read_text()
    assert "textFormat: Text.PlainText" in qml  # the title is untrusted content
    # "Everything else is the stock widget's behaviour ... the stock IPC target keeps
    # working" (README): the built-in moduleName, both clicks (the two identical stock
    # close branches merged into one ||), the tooltip, and the title on two lines.
    assert 'moduleName: "omarchy.active-window"' in qml
    assert "mouse.button === Qt.MiddleButton || mouse.button === Qt.RightButton" in qml
    assert "root.toplevel.close()" in qml and "root.toplevel.activate()" in qml
    assert "bar.showTooltip(root, root.title)" in qml and "bar.hideTooltip(root)" in qml
    assert "maximumLineCount: 2" in qml
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    p = subprocess.run([qmllint, "--bare", str(PLUGIN / "ActiveWindow.qml")], capture_output=True)
    assert p.returncode == 0, p.stderr


def test_omarchy_plugin_validate_accepts_the_installed_link(box) -> None:
    omarchy = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")
    validate = Path(omarchy, "bin/omarchy-plugin-validate")
    if not validate.exists():
        pytest.skip("no installed Omarchy to validate against")
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert box.run(INSTALL).returncode == 0
    # The trailing slash is load-bearing: find prints the start point itself (:115).
    proc = subprocess.run([str(validate), f"{box.home / LINK}/"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
