"""modules/bar-active-window: the link, the one enable, and the widget itself.

Everything runs against the `box` fixture (repo-root conftest.py): a throwaway
HOME and a PATH whose `omarchy-*` are recording fakes, so no test can reach the
developer's bar. The one real Omarchy command a test runs is
`omarchy-plugin-validate`, by absolute path, skipped where Omarchy is absent
(CI) — the shape a stranger's `omarchy plugin add` would hold the folder to.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
PLUGIN = MODULE / "plugin"
ID = "hyprconf.active-window"

# An omarchy-plugin-list that already knows the id, so the discovery wait
# (bin/omarchy-plugin-add:164-171, the loop the install copies) breaks at once.
LIST_KNOWS_IT = f'printf \'[{{"id": "{ID}"}}]\\n\'\n'


def _link(box) -> Path:
    return box.home / ".config" / "omarchy" / "plugins" / ID


def _marker(box) -> Path:
    return box.home / ".local" / "state" / "hyprconf" / "active-window-applied"


def _snapshot(root: Path) -> dict[str, tuple]:
    """Every path under root with what it is and when it changed — the form a
    "a second run writes nothing" assertion compares. Symlinks are never
    followed: the link's target is part of what must not change."""
    out: dict[str, tuple] = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(base) / name
            stat = path.lstat()
            target = os.readlink(path) if path.is_symlink() else None
            out[str(path.relative_to(root))] = (stat.st_mode, stat.st_mtime_ns, target)
    return out


def _install(box, **kwargs) -> subprocess.CompletedProcess:
    return box.run(INSTALL, **kwargs)


# ---------------------------------------------------------------------------
# The install
# ---------------------------------------------------------------------------


def test_the_plugin_folder_is_linked_and_enabled_once(box) -> None:
    """A symlink, not a copy: the third-party scan follows one
    (PluginRegistry.qml:710-714) and a `git pull` in the checkout is then the
    update. The rescan is what tells the shell about it — its inotify watch
    never descends a link (:663-674) — and the enable carries no placement,
    because a clonedFrom copy takes the stock widget's slot (:529-534)."""
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    proc = _install(box)
    assert proc.returncode == 0, proc.stderr
    assert _link(box).is_symlink()
    assert os.readlink(_link(box)) == str(PLUGIN)
    assert (_link(box) / "manifest.json").is_file()
    assert "omarchy-shell shell rescanPlugins" in box.calls
    assert f"omarchy-plugin-enable {ID}" in box.calls
    assert not any(c.startswith("omarchy-plugin-enable omarchy.") for c in box.calls)
    assert not any("--section" in c for c in box.calls)
    assert _marker(box).exists()
    assert "undo" in proc.stdout


def test_a_second_run_writes_nothing_and_re_enables_nothing(box) -> None:
    """The post-update hook re-runs every module after every omarchy-update:
    the second run may ask for a rescan (cheap, and the only way a pulled
    change reaches the shell) but must touch no file and enable nothing —
    `omarchy plugin disable` is the user's and has to stick."""
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert _install(box).returncode == 0
    before = _snapshot(box.home)
    box.reset()

    proc = _install(box)
    assert proc.returncode == 0, proc.stderr
    assert _snapshot(box.home) == before
    assert "omarchy-plugin-enable" not in box.commands
    assert "omarchy-plugin-list" not in box.commands
    assert "omarchy-bar" not in box.commands


def test_a_real_directory_where_the_link_goes_is_moved_aside_once(box) -> None:
    """The pre-module installer synced a real folder into that path (and a
    stranger may have copied one in by hand). It is moved aside, never
    deleted — and only the once: the second run finds the link it made."""
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    plugins = box.home / ".config" / "omarchy" / "plugins"
    old = plugins / ID
    old.mkdir(parents=True)
    (old / "ActiveWindow.qml").write_text("// the copy from before the modules\n")

    assert _install(box).returncode == 0
    assert _link(box).is_symlink()
    backups = sorted(plugins.glob(f".{ID}.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "ActiveWindow.qml").read_text().startswith("// the copy")

    assert _install(box).returncode == 0
    assert sorted(plugins.glob(f".{ID}.bak.*")) == backups


def test_an_omarchy_plugin_add_checkout_is_left_to_omarchy(box) -> None:
    """`omarchy plugin add <url>` lands the same id as a git checkout, which
    `omarchy plugin update` fast-forwards and which refuses a non-git folder.
    Replacing it with a link would throw away the user's checkout."""
    plug = box.home / ".config" / "omarchy" / "plugins" / ID
    plug.mkdir(parents=True)
    (plug / ".git").mkdir()
    (plug / "ActiveWindow.qml").write_text("// the user's checkout\n")

    proc = _install(box)
    assert proc.returncode == 0, proc.stderr
    assert not plug.is_symlink()
    assert (plug / "ActiveWindow.qml").read_text() == "// the user's checkout\n"
    assert "omarchy plugin update" in proc.stdout
    assert box.commands == []
    assert not _marker(box).exists()


def test_no_shell_answering_leaves_the_marker_for_the_next_run(box) -> None:
    """A TTY or SSH run has no live shell: omarchy-plugin-list exits 1 the
    moment omarchy-shell reports "is not running", so there is nothing to wait
    for, the enable fails — and the module still exits 0 with the link in
    place, the marker unwritten, and the enable retried on the next run."""
    box.stub("omarchy-plugin-list", "exit 1\n")
    box.stub("omarchy-plugin-enable", "exit 1\n")
    proc = _install(box)
    assert proc.returncode == 0, proc.stderr
    assert _link(box).is_symlink()
    assert not _marker(box).exists()
    assert "next run" in proc.stdout
    assert box.commands.count("omarchy-plugin-list") == 1

    box.reset()
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    box.stub("omarchy-plugin-enable", "exit 0\n")
    assert _install(box).returncode == 0
    assert f"omarchy-plugin-enable {ID}" in box.calls
    assert _marker(box).exists()


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


def test_undo_disables_the_plugin_and_takes_the_link_away(box) -> None:
    """Stock comes back through Omarchy's own restoreCloneSource
    (PluginRegistry.qml:555) — the module only asks for the disable, drops the
    link and the marker, and rescans. The checkout it pointed at is untouched."""
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert _install(box).returncode == 0
    box.reset()

    proc = box.undo("bar-active-window")
    assert proc.returncode == 0, proc.stderr
    assert f"omarchy-plugin-disable {ID}" in box.calls
    assert "omarchy-shell shell rescanPlugins" in box.calls
    assert not _link(box).exists() and not _link(box).is_symlink()
    assert not _marker(box).exists()
    assert (PLUGIN / "manifest.json").is_file()


def test_undo_leaves_a_folder_that_is_not_the_modules_link_whole(box) -> None:
    """Undo removes the module's own symlink and nothing else: a real
    directory at that path is somebody else's copy — the pre-module sync, or
    one dropped in by hand — and deleting it would throw away their files."""
    plug = box.home / ".config" / "omarchy" / "plugins" / ID
    plug.mkdir(parents=True)
    (plug / "ActiveWindow.qml").write_text("// not ours\n")

    proc = box.undo("bar-active-window")
    assert proc.returncode == 0, proc.stderr
    assert (plug / "ActiveWindow.qml").read_text() == "// not ours\n"
    assert f"omarchy-plugin-disable {ID}" in box.calls


def test_undo_on_a_machine_that_never_installed_it_is_a_no_op(box) -> None:
    """`install.sh --undo` runs every module's undo, installed or not."""
    proc = box.undo("bar-active-window")
    assert proc.returncode == 0, proc.stderr
    assert _snapshot(box.home) == {}


def test_install_after_undo_enables_it_again(box) -> None:
    """Undo removes the marker, so the choice can be made again."""
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert _install(box).returncode == 0
    assert box.undo("bar-active-window").returncode == 0
    box.reset()
    assert _install(box).returncode == 0
    assert f"omarchy-plugin-enable {ID}" in box.calls
    assert _marker(box).exists()


# ---------------------------------------------------------------------------
# The payload
# ---------------------------------------------------------------------------


def test_the_manifest_is_the_clone_contract_and_nothing_the_shell_defaults(box) -> None:
    """What the bar turns on: the stock widget this copy claims (clonedFrom —
    what makes the shell swap it into that slot and `omarchy plugin disable`
    restore stock), the entry point it loads, and where a widget with no stock
    entry to replace goes (defaultSection left, anchored after
    omarchy.workspaces by PluginRegistry.qml:270-275). barWidget.displayName,
    .description and .allowMultiple are NOT here: shell.qml:1402-1405 falls
    back to the manifest's own name/description and to allowMultiple false, so
    shipping them into a stranger's $HOME restates the lines above them."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["schemaVersion"] == 1
    assert manifest["id"] == ID
    assert manifest["kinds"] == ["bar-widget"]
    assert manifest["entryPoints"] == {"barWidget": "ActiveWindow.qml"}
    assert manifest["omarchy"] == {"clonedFrom": "omarchy.active-window"}
    assert manifest["barWidget"] == {"category": "Compositor", "defaultSection": "left"}


def test_the_folder_carries_what_a_plugin_repository_needs(box) -> None:
    """Published on its own it is a plugin and nothing else: the manifest, the
    widget, its README and Omarchy's MIT NOTICE — which every copy of its code
    must carry — and no overlay paths inside it."""
    assert {p.name for p in PLUGIN.iterdir()} == {
        "manifest.json",
        "ActiveWindow.qml",
        "README.md",
        "NOTICE",
    }
    assert "MIT" in (PLUGIN / "NOTICE").read_text()
    assert not any(p.is_symlink() for p in PLUGIN.rglob("*"))


def test_the_widget_keeps_the_stock_behaviours_and_the_stock_ipc_id(box) -> None:
    """The copy re-lays the title out; everything else the stock widget does —
    the tooltip, click to focus, middle- or right-click to close — and the id
    `omarchy bar` addresses it by have to survive the rewrite. The two
    identical close branches of the stock file (widgets/ActiveWindow.qml:53-57)
    are merged here into one `||`: same behaviour, a source-only delta its
    header names so a re-sync re-applies it deliberately."""
    qml = (PLUGIN / "ActiveWindow.qml").read_text()
    assert 'moduleName: "omarchy.active-window"' in qml
    assert "Qt.MiddleButton || mouse.button === Qt.RightButton" in qml
    assert "root.toplevel.close()" in qml and "root.toplevel.activate()" in qml
    assert "showTooltip(root, root.title)" in qml and "hideTooltip(root)" in qml
    assert "maximumLineCount: 2" in qml


def test_the_widget_paints_plain_text_and_never_sizes_off_its_parent(box) -> None:
    """A window title is untrusted text: without `textFormat: Text.PlainText`
    a title containing markup renders as rich text. And a widget whose
    implicit size reads `parent` closes a binding loop the ModuleSlot breaks
    by dropping the binding — zero height, nothing logged, a gap in the bar."""
    code = "\n".join(
        re.sub(r"//.*", "", line) for line in (PLUGIN / "ActiveWindow.qml").read_text().splitlines()
    )
    assert re.search(r"\bText\s*\{", code), "no Text block to check"
    assert "textFormat: Text.PlainText" in code
    assert not [
        line
        for line in code.splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]


def test_the_widget_qml_parses(box) -> None:
    """A QML syntax error is an empty bar slot with nothing in any log.
    `qmllint --bare` parses without the module imports."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    proc = subprocess.run(
        [qmllint, "--bare", str(PLUGIN / "ActiveWindow.qml")], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_omarchy_plugin_validate_accepts_the_installed_link(box) -> None:
    """What `omarchy plugin add` would hold a split-out repository to, run on
    the link the module makes: the validator's `find` prints the starting
    point itself for a bare symlink, so the trailing slash is load-bearing
    (bin/omarchy-plugin-validate:115). Skips without the installed Omarchy —
    one of the skips AGENTS.md › Gates and CI budgets for."""
    # bin/ is a symlink into /usr/bin; OMARCHY_PATH is the seam every
    # needs-Omarchy probe keys on, so an empty one reproduces CI's skips.
    validate = (
        Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "bin/omarchy-plugin-validate"
    )
    if not validate.exists():
        pytest.skip("no installed Omarchy to validate against")
    box.stub("omarchy-plugin-list", LIST_KNOWS_IT)
    assert _install(box).returncode == 0
    proc = subprocess.run(
        [str(validate), f"{_link(box)}/"], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
