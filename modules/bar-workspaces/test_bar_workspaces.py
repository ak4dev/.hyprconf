"""modules/bar-workspaces: the link, the one-time enable, the undo, on `box`.
The shape every plugin folder keeps: tests/test_plugins_contract.py."""

import json
import os
import subprocess
from pathlib import Path

import pytest

INSTALL = Path(__file__).parent / "install"
PLUGIN = Path(__file__).parent / "plugin"
ID = "hyprconf.workspaces"
LINK = f".config/omarchy/plugins/{ID}"
MARKER = ".local/state/hyprconf/workspaces-applied"
VALIDATE = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"), "bin/omarchy-plugin-validate")
# A shell that answers the discovery poll (bin/omarchy-plugin-add:163-171).
LISTS_THE_PLUGIN = f'printf \'[{{"id":"{ID}"}}]\\n\'\n'


def snapshot(root: Path) -> dict[str, tuple]:
    out = {}
    for p in sorted(root.rglob("*")):
        v = f"-> {p.readlink()}" if p.is_symlink() else p.read_bytes() if p.is_file() else "dir"
        out[str(p.relative_to(root))] = (v, p.lstat().st_mtime_ns)
    return out


def test_links_the_plugin_folder_and_enables_it_once(box):
    """The enable carries NO placement: that is what lets the clonedFrom swap keep the stock widget's slot (PluginRegistry.qml:528-534 vs :545-546)."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    assert (box.home / LINK).readlink() == PLUGIN
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    assert ["omarchy-shell", "-q", "shell", "rescanPlugins"] in box.calls_of("omarchy-shell")
    assert (box.home / MARKER).is_file() and not {"sudo", "omarchy-bar"} & set(box.commands)


def test_a_second_run_writes_nothing_and_enables_nothing(box):
    """The hook re-runs every module after every omarchy-update, and the widget never goes back on a bar the user took it off (rule 5)."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    before = snapshot(box.home)
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert snapshot(box.home) == before
    assert box.commands == ["omarchy-shell"]


def test_a_git_checkout_of_the_same_id_is_left_to_omarchy(box):
    (box.home / LINK / ".git").mkdir(parents=True)
    proc = box.run(INSTALL)
    assert proc.returncode == 0 and "omarchy plugin update" in proc.stdout
    assert box.commands == [] and not (box.home / LINK).is_symlink()


def test_a_real_directory_is_moved_aside_once_and_replaced_by_the_link(box):
    """Moved to `.<id>.bak.<timestamp>`, what omarchy-plugin-remove does with a folder it did not clone (bin/omarchy-plugin-remove:106) — never deleted."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    (synced := box.home / LINK).mkdir(parents=True)
    (synced / "manifest.json").write_text('{"id": "old"}\n')
    assert box.run(INSTALL).returncode == 0
    assert synced.readlink() == PLUGIN
    (backup,) = synced.parent.glob(f".{ID}.bak.*")
    assert (backup / "manifest.json").read_text() == '{"id": "old"}\n'


def test_no_shell_answering_leaves_the_marker_unwritten_for_the_next_run(box):
    """The link is still made and the run still succeeds — it must not fail the module loop — and the next in-session run does the enable."""
    box.stub("omarchy-plugin-list", "exit 1\n")  # what it does with no shell answering
    box.stub("omarchy-plugin-enable", "exit 1\n")
    proc = box.run(INSTALL)
    assert proc.returncode == 0 and "next run" in proc.stdout
    assert (box.home / LINK).is_symlink() and not (box.home / MARKER).exists()
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    box.stub("omarchy-plugin-enable")
    assert box.run(INSTALL).returncode == 0
    assert box.calls_of("omarchy-plugin-enable")[-1] == ["omarchy-plugin-enable", ID]
    assert (box.home / MARKER).is_file()


def test_undo_disables_the_plugin_and_takes_the_link_and_marker_away(box):
    """Disabled first, while still installed: the clonedFrom entry is what hands the slot back to the stock widget (PluginRegistry.qml:555 -> :441)."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    box.reset()
    assert box.undo("bar-workspaces").returncode == 0
    assert box.calls[0] == f"omarchy-plugin-disable {ID}"
    assert not (box.home / LINK).exists(follow_symlinks=False) and not (box.home / MARKER).exists()
    assert ["omarchy-shell", "-q", "shell", "rescanPlugins"] in box.calls_of("omarchy-shell")


def test_undo_leaves_a_real_directory_it_never_made(box):
    """`rm -f` on a directory fails, which would take the whole undo down with it."""
    (folder := box.home / LINK).mkdir(parents=True)
    (marker := box.home / MARKER).parent.mkdir(parents=True)
    marker.touch()
    assert box.undo("bar-workspaces").returncode == 0
    assert folder.is_dir() and not folder.is_symlink() and not marker.exists()


def test_manifest_declares_the_slot_and_entry_point_the_shell_reads(box):
    """No `barWidget.defaultSection` — the clonedFrom swap inherits the stock widget's slot — and none of the keys shell.qml:1400-1405 already defaults."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID and manifest["kinds"] == ["bar-widget"]
    assert manifest["entryPoints"] == {"barWidget": "Workspaces.qml"}
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.workspaces"
    assert manifest["barWidget"] == {"category": "Compositor"}


def test_the_installed_link_passes_omarchy_plugin_validate(box):
    """The real validator on the installed link, with the trailing slash its `find` needs (bin/omarchy-plugin-validate:115) — a budgeted Omarchy skip."""
    if not VALIDATE.is_file():
        pytest.skip("no installed omarchy-plugin-validate")
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    cmd = ["bash", str(VALIDATE), f"{box.home / LINK}/"]
    env = {"PATH": "/usr/bin:/bin", "HOME": str(box.home)}
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    assert proc.returncode == 0, proc.stderr
