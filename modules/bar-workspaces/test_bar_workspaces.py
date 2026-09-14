"""modules/bar-workspaces: the link, the one-time enable, the undo — and the
contract the plugin folder keeps so it can be published on its own.

HERMETIC: every run is `box`'s throwaway machine (repo-root conftest.py); the
only real Omarchy command is `omarchy-plugin-validate`, which reads a folder
and writes nothing, and the test skips where it is not installed. CI has no
Omarchy: the validator's checks ported to Python run there instead, over every
shipped folder, in tests/test_plugins_contract.py.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
PLUGIN = MODULE / "plugin"
ID = "hyprconf.workspaces"
# Omarchy's own validator (pure: reads the manifest and the tree).
PLUGIN_VALIDATE = Path("/usr/share/omarchy/bin/omarchy-plugin-validate")

# A shell that answers: what the install script polls for before the enable
# (bin/omarchy-plugin-add:163-171 is the shape it copies). Without it the fake
# omarchy-plugin-list prints nothing and the poll spends its full 2 s.
LISTS_THE_PLUGIN = f'printf \'[{{"id":"{ID}"}}]\\n\'\n'


def install_path(box) -> Path:
    return box.home / ".config/omarchy/plugins" / ID


def marker_path(box) -> Path:
    return box.home / ".local/state/hyprconf/workspaces-applied"


def snapshot(root: Path) -> dict[str, tuple]:
    """Every path under `root` as (symlink target | bytes, mtime) — what a
    second run has to leave exactly as it found."""
    out = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            out[rel] = (f"-> {path.readlink()}", path.lstat().st_mtime_ns)
        elif path.is_file():
            out[rel] = (path.read_bytes(), path.stat().st_mtime_ns)
        else:
            out[rel] = ("dir", None)
    return out


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def test_links_the_plugin_folder_and_enables_it_once(box) -> None:
    """The folder is a symlink into the checkout — Omarchy's third-party scan
    follows one (PluginRegistry.qml:712-713) — and the enable carries NO
    placement, which is what lets the clonedFrom swap keep the stock widget's
    slot (PluginRegistry.qml:530-534 vs :545-546)."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    proc = box.run(INSTALL)
    assert proc.returncode == 0, proc.stderr
    link = install_path(box)
    assert link.is_symlink() and link.readlink() == PLUGIN
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    assert ["omarchy-shell", "-q", "shell", "rescanPlugins"] in box.calls_of("omarchy-shell")
    assert marker_path(box).is_file()


def test_a_second_run_writes_nothing_and_enables_nothing(box) -> None:
    """The post-update hook re-runs every module after every omarchy-update:
    byte-stable, and the widget is never put back on a bar the user took it
    off (AGENTS.md rule 5)."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    before = snapshot(box.home)
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert snapshot(box.home) == before
    assert "omarchy-plugin-enable" not in box.commands


def test_never_touches_the_bar_layout_or_the_widget_settings(box) -> None:
    """This module links and enables, nothing else: the format and the centre
    anchor are the clock's business, and `omarchy bar set omarchy.workspaces`
    has no key either widget reads."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    assert "omarchy-bar" not in box.commands


def test_the_no_sudo_hook_run_still_links_and_enables(box) -> None:
    """The post-update hook runs every module with --no-packages
    (HYPRCONF_NO_SUDO): this module needs no sudo at all, so that run is the
    full run — which is what makes the hook the retry for an enable that had
    no shell to talk to."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    proc = box.run(INSTALL, env={"HYPRCONF_NO_SUDO": "1"})
    assert proc.returncode == 0, proc.stderr
    assert install_path(box).is_symlink()
    assert marker_path(box).is_file()
    assert "sudo" not in box.commands


def test_a_git_checkout_of_the_same_id_is_left_to_omarchy(box) -> None:
    """`omarchy plugin add <url>` lands this id as a git checkout that
    `omarchy plugin update` fast-forwards (bin/omarchy-plugin-update refuses a
    non-git folder): the module keeps its hands off it."""
    checkout = install_path(box)
    (checkout / ".git").mkdir(parents=True)
    (checkout / "manifest.json").write_text("{}\n")
    before = snapshot(box.home)
    proc = box.run(INSTALL)
    assert proc.returncode == 0
    assert "omarchy plugin update" in proc.stdout
    assert snapshot(box.home) == before
    assert box.commands == []


def test_a_real_directory_is_moved_aside_once_and_replaced_by_the_link(box) -> None:
    """The pre-module installer synced a real directory here (and a hand-drop
    is the same shape). It is moved to `.<id>.bak.<timestamp>` — what
    omarchy-plugin-remove does with a folder it did not clone
    (bin/omarchy-plugin-remove:106) — never deleted."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    synced = install_path(box)
    synced.mkdir(parents=True)
    (synced / "manifest.json").write_text('{"id": "old"}\n')
    assert box.run(INSTALL).returncode == 0
    assert synced.is_symlink() and synced.readlink() == PLUGIN
    backups = list(synced.parent.glob(f".{ID}.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "manifest.json").read_text() == '{"id": "old"}\n'


def test_a_link_left_by_an_older_checkout_is_repointed(box) -> None:
    """The checkout moved (or the module was run from a second clone): the
    link is rewritten, and nothing else about the run changes."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    link = install_path(box)
    link.parent.mkdir(parents=True)
    link.symlink_to(box.tmp / "old-checkout/plugins/hyprconf-workspaces")
    assert box.run(INSTALL).returncode == 0
    assert link.readlink() == PLUGIN


def test_no_shell_answering_leaves_the_marker_unwritten_for_the_next_run(box) -> None:
    """A TTY or SSH run has no shell to enable against: the link is still
    made, the run still succeeds (it must not fail the module loop), and the
    next in-session run does the enable."""
    box.stub("omarchy-plugin-list", "exit 1\n")  # what it does with no shell
    box.stub("omarchy-plugin-enable", "exit 1\n")
    proc = box.run(INSTALL)
    assert proc.returncode == 0
    assert "next run" in proc.stdout
    assert install_path(box).is_symlink()
    assert not marker_path(box).exists()

    box.stub("omarchy-plugin-enable", "exit 0\n")
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    assert marker_path(box).is_file()


# ---------------------------------------------------------------------------
# undo
# ---------------------------------------------------------------------------


def test_undo_disables_the_plugin_and_takes_the_link_and_marker_away(box) -> None:
    """Disable first, while the plugin is still installed: the clonedFrom
    entry is what hands the slot back to the stock widget
    (PluginRegistry.qml:555 -> restoreCloneSource:441)."""
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    box.reset()
    proc = box.undo("bar-workspaces")
    assert proc.returncode == 0
    assert box.commands.index("omarchy-plugin-disable") == 0
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", ID]]
    assert not install_path(box).exists(follow_symlinks=False)
    assert not marker_path(box).exists()
    assert ["omarchy-shell", "-q", "shell", "rescanPlugins"] in box.calls_of("omarchy-shell")


def test_undo_leaves_a_real_directory_it_never_made(box) -> None:
    """Undo removes the module's link, not a folder: an `omarchy plugin add`
    checkout and the pre-module synced copy are both real directories at this
    path, neither installed by this module — and `rm -f` on one fails, which
    would take the whole undo down with it."""
    folder = install_path(box)
    (folder / ".git").mkdir(parents=True)
    (folder / "manifest.json").write_text('{"id": "theirs"}\n')
    marker_path(box).parent.mkdir(parents=True)
    marker_path(box).touch()
    proc = box.undo("bar-workspaces")
    assert proc.returncode == 0, proc.stderr
    assert (folder / "manifest.json").read_text() == '{"id": "theirs"}\n'
    assert not marker_path(box).exists()


def test_undo_on_a_machine_that_never_installed_it_is_a_no_op(box) -> None:
    proc = box.undo("bar-workspaces")
    assert proc.returncode == 0
    assert box.files() == set()


# ---------------------------------------------------------------------------
# the plugin folder, as a repository of its own
# ---------------------------------------------------------------------------


def test_manifest_declares_the_slot_and_entry_point_the_shell_reads(box) -> None:
    """The keys the shell actually reads: id, kinds, entryPoints, clonedFrom.
    No `barWidget.defaultSection` — the clonedFrom swap inherits the stock
    widget's slot — and none of the keys shell.qml:1400-1405 already defaults
    (`barWidget.description` duplicates `description`, `allowMultiple: false`
    is the default)."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID
    assert manifest["kinds"] == ["bar-widget"]
    assert manifest["entryPoints"] == {"barWidget": "Workspaces.qml"}
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.workspaces"
    assert set(manifest["barWidget"]) == {"displayName", "category"}


def test_the_widget_lists_only_the_workspaces_that_exist(box) -> None:
    """No fixed pill set and no id cap — stock's are
    `var ids = [1, 2, 3, 4, 5]` and `id <= 10`
    (shell/plugins/bar/widgets/Workspaces.qml:21,26, Omarchy 4.0.3-1) — and
    the stock IPC id is kept as moduleName so `omarchy bar` still addresses
    it."""
    qml = (PLUGIN / "Workspaces.qml").read_text()
    assert "[1, 2, 3, 4, 5]" not in qml and "id <= 10" not in qml
    assert 'moduleName: "omarchy.workspaces"' in qml


def test_the_widget_never_sizes_itself_off_its_parent(box) -> None:
    """Omarchy's ModuleSlot takes its height from the widget's implicit size,
    so `implicitHeight: parent.height` closes a binding loop — QML drops the
    binding, and the widget is zero-height with nothing in any log."""
    offenders = [
        line.strip()
        for line in (PLUGIN / "Workspaces.qml").read_text().splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]
    assert offenders == []


def test_every_text_element_declares_the_plain_text_format(box) -> None:
    """Omarchy 4.0.2 added `textFormat: Text.PlainText` to its own stock
    widgets (shell/Ui/WidgetButton.qml:77) because a Text whose `text:` is a
    runtime string renders markup as rich text under Qt's default AutoText.
    Upstream's scanner lives in Omarchy's git repository, not in the package
    (test/shell.d/qml-text-format-scan.py), so this is the rule itself: every
    Text block declares the line, literal-only ones included."""
    code = "\n".join(
        line.split("//")[0] for line in (PLUGIN / "Workspaces.qml").read_text().splitlines()
    )
    blocks = list(re.finditer(r"(?:^|[:\s])(?:[A-Za-z_]\w*\.)?Text\s*\{", code))
    assert blocks, "no Text block found — has the widget stopped drawing text?"
    for match in blocks:
        depth, i = 1, match.end()
        while depth and i < len(code):
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        assert "textFormat: Text.PlainText" in code[match.end() : i]


def test_the_folder_carries_omarchys_mit_notice_and_nothing_of_the_overlay(box) -> None:
    """It is a clonedFrom derivative of Omarchy's MIT code, and `omarchy
    plugin add` installs it with no overlay around it: nothing of the
    installer's (~/.local/bin, a substituted path) can work there."""
    assert (PLUGIN / "NOTICE").is_file() and (PLUGIN / "README.md").is_file()
    for path in sorted(PLUGIN.rglob("*")):
        assert not path.is_symlink(), f"{path}: symlinks are refused inside a plugin folder"
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in (".local/bin", "@HYPRCONF_DIR@"):
                assert token not in text, f"{path.name} mentions {token}"


def test_the_installed_link_passes_omarchy_plugin_validate(box) -> None:
    """The real validator, against the installed path — a link, so with the
    trailing slash its `find` needs (bin/omarchy-plugin-validate:115 prints
    the starting point itself without -L). Skips where Omarchy is not
    installed — one of the seven needs-the-installed-Omarchy skips AGENTS.md
    budgets for (› Gates and CI)."""
    if not PLUGIN_VALIDATE.is_file():
        pytest.skip("no installed omarchy-plugin-validate")
    box.stub("omarchy-plugin-list", LISTS_THE_PLUGIN)
    assert box.run(INSTALL).returncode == 0
    proc = subprocess.run(
        ["bash", str(PLUGIN_VALIDATE), f"{install_path(box)}/"],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin", "HOME": str(box.home)},
    )
    assert proc.returncode == 0, proc.stderr


def test_the_widget_qml_parses(box) -> None:
    """A QML syntax error is an empty bar slot with nothing in any log.
    `qmllint --bare` parses without the module imports."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the widget")
    proc = subprocess.run(
        [qmllint, "--bare", str(PLUGIN / "Workspaces.qml")], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
