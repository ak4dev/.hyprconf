"""The contract every shipped plugin folder keeps, the same for all four bar modules: the
omarchy-plugin-validate port (CI has no Omarchy) and one run of the real thing, the shape a
folder needs as a repository of its own, the Text and implicit-size rules, a qmllint parse,
the facade-member pin — and, since the four installs are one mechanism (modules/bar-plugin.sh),
the install and undo cases each module used to repeat: link, rescan, the one enable, the
checkout it leaves alone, the folder it moves aside, no shell answering, and the way back."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import (
    NEEDS_OMARCHY,
    OMARCHY,
    PLUGIN_ENABLE,
    PLUGIN_LIST,
    REPO_ROOT,
    Box,
    bar_shell,
)

FOLDERS = sorted(REPO_ROOT.glob("modules/*/plugin"))
assert FOLDERS, "no plugin folders found"
per_folder = pytest.mark.parametrize("folder", FOLDERS, ids=lambda f: f.parent.name)

# bin/omarchy-plugin-validate (Omarchy 4.0.3-1): its id regex, required fields and
# kind -> entry-point table.
PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REQUIRED = ("id", "name", "version", "kinds", "entryPoints")
KIND_ENTRY_POINTS = {
    "bar": "bar",
    "bar-widget": "barWidget",
    "menu": "menu",
    "overlay": "overlay",
    "panel": "panel",
    "service": "service",
}
BARE_ARGV = re.compile(r'command:\s*\[\s*"(hyprconf-[^"]*)"')


def walk(folder: Path):
    """Every path under a plugin folder, .git pruned the way the validator prunes it."""
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in dirnames + sorted(filenames):
            yield Path(dirpath) / name


def validator_problems(folder: Path) -> list[str]:
    """What omarchy-plugin-validate refuses, check for check, symlinks included (its own
    refusal, :115-116). jq's `==` is type-aware: `true` is not 1."""
    path = folder / "manifest.json"
    if not path.is_file():
        return ["missing manifest.json"]
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"manifest.json is not valid JSON: {exc}"]
    if not isinstance(m, dict):
        return ["manifest.json is not a JSON object"]
    out = [f"manifest missing '{f}'" for f in REQUIRED if f not in m]
    schema = m.get("schemaVersion")
    if isinstance(schema, bool) or schema != 1:
        out.append("unsupported or missing schemaVersion (expected 1)")
    pid = m.get("id")
    if not isinstance(pid, str) or not pid:
        out.append("manifest 'id' is empty")
    elif not PLUGIN_ID_RE.match(pid) or ".." in pid or pid.startswith("omarchy."):
        out.append(f"invalid plugin id '{pid}'")
    kinds = m.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        out.append("'kinds' must be a non-empty array")
        kinds = []
    eps = m.get("entryPoints")
    if not isinstance(eps, dict):
        out.append("'entryPoints' must be an object")
        eps = {}
    widget = m.get("barWidget")
    if isinstance(widget, dict) and "defaultSection" in widget:
        if widget["defaultSection"] not in ("left", "center", "right"):
            out.append("'barWidget.defaultSection' must be left, center, or right")
    for key, ep in eps.items():
        if not isinstance(ep, str) or not ep:
            out.append(f"entry point '{key}' is empty")
        elif "\n" in ep or ep.startswith("/") or ".." in ep or not (folder / ep).is_file():
            out.append(f"entry point '{key}' is not a relative path to a file here: '{ep}'")
    for kind, ep_key in KIND_ENTRY_POINTS.items():
        if kind in kinds and ep_key not in eps:
            out.append(f"kind '{kind}' requires an 'entryPoints.{ep_key}' to load")
    out += [f"symlink inside the folder: {p}" for p in walk(folder) if p.is_symlink()]
    return out


def publishable_problems(folder: Path) -> list[str]:
    """What breaks the folder as a repository of its own: no README, no MIT NOTICE on a
    clonedFrom copy, a feeder without its exec bit, anything of the overlay's around it."""
    out = [] if (folder / "README.md").is_file() else ["no README.md at the folder root"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("omarchy", {}).get("clonedFrom") and not (folder / "NOTICE").is_file():
        out.append("a clonedFrom copy of Omarchy's MIT code with no NOTICE")
    for path in (p for p in walk(folder) if p.is_file()):
        rel, text = path.relative_to(folder), path.read_text(encoding="utf-8", errors="replace")
        out += [f"{rel} mentions {n}" for n in (".local/bin", "@HYPRCONF_DIR@") if n in text]
        if path.suffix == ".qml":
            out += [f"{rel} runs a bare {m.group(1)}" for m in BARE_ARGV.finditer(text)]
        if text.startswith("#!") and not os.access(path, os.X_OK):
            out.append(f"{rel} has a shebang but is not executable")
    return out


# Omarchy 4.0.2's Text rule (shell/plugins/bar/widgets/ActiveWindow.qml:32, shell/Ui/
# WidgetButton.qml:77; its scan lives in Omarchy's git repository, not the package): a runtime
# string renders markup under Qt's AutoText. Blunter here: every Text block declares the line.
TEXT_BLOCK = re.compile(r"(?:^|[:\s])(?:[A-Za-z_]\w*\.)?Text\s*\{")
COMMENT = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|//.*$""")


def qml_code(path: Path) -> str:
    """The file with its `//` comments off (one inside a string stays)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(COMMENT.sub(lambda m: m.group(1) or "", ln) for ln in lines)


def text_format_problems(path: Path) -> list[str]:
    code, out = qml_code(path), []
    for match in TEXT_BLOCK.finditer(code):
        depth, i = 1, match.end()
        while depth and i < len(code):
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        if "textFormat: Text.PlainText" not in code[match.end() : i]:
            out.append(f"{path.relative_to(REPO_ROOT)}:{code.count(chr(10), 0, match.start()) + 1}")
    return out


# Ui/PluginBarApi.qml and services/PluginShellApi.qml (Omarchy 4.0.3-1): the facades an
# INSTALLED third-party widget gets in place of the host Bar and ShellRoot (plugins/bar/
# Bar.qml:2002-2003, shell.qml:739-743). Their public members are the whole contract;
# anything else a widget reads off `bar` is undefined at runtime and says nothing. Where
# Omarchy is installed the real files are read and the pins checked against them.
PLUGIN_BAR_API = (
    "activePopout",
    "background",
    "barForeground",
    "barSize",
    "centerHoverRevealSuppressed",
    "centerSectionRevealHeld",
    "clickTargets",
    "fontFamily",
    "foreground",
    "foregroundAnimationEnabled",
    "foreignPopoutMarker",
    "hideTooltip",
    "layoutConfig",
    "moduleName",
    "moduleWidgets",
    "pluginId",
    "position",
    "registerClickTarget",
    "releasePopout",
    "requestPopout",
    "run",
    "setCenterHoverRevealSuppressed",
    "shell",
    "showTooltip",
    "switchPanelFrom",
    "targetBelongsToWindow",
    "transparent",
    "unregisterClickTarget",
    "urgent",
    "vertical",
)
PLUGIN_SHELL_API = (
    "appLibrary",
    "bar",
    "barConfig",
    "firstPartyServiceFor",
    "hide",
    "idleConfig",
    "isPluginOpen",
    "mutateShellConfig",
    "pluginId",
    "pluginShellForBarEntry",
    "serviceFor",
    "summon",
    "toggle",
    "updateEntryInline",
)
OMARCHY_SHELL = OMARCHY / "shell"
DECLARES_RE = re.compile(
    r"^\s*(?:readonly\s+)?(?:required\s+)?(?:property\s+\S+|function)\s+(\w+)", re.M
)
# `bar.x`, `bar?.shell?.x`; `root.`/`this.` stripped first, so `Style.bar.iconSlot` is not one.
OWNER_RE = re.compile(r"\b(?:root|this)\s*\??\.\s*")
MEMBER_RE = re.compile(r"(?<![\w.])bar\s*\??\.\s*(?:shell\s*\??\.\s*)?([A-Za-z_]\w*)")


@per_folder
def test_plugin_folder_is_valid_and_publishable_alone(folder: Path) -> None:
    """The contract `omarchy plugin add` gates a repository on, pinned where publishing is
    gated: CI. The real validator runs below, where Omarchy is installed."""
    assert validator_problems(folder) + publishable_problems(folder) == []
    # Frozen: the validator checks presence only (bin/omarchy-plugin-validate:44-47),
    # `plugin update` is a fast-forward that never opens it, and every first-party one is 1.0.0.
    assert json.loads((folder / "manifest.json").read_text())["version"] == "1.0.0"


@per_folder
def test_plugin_text_never_renders_runtime_strings_as_rich_text(folder: Path) -> None:
    problems = [p for qml in sorted(folder.rglob("*.qml")) for p in text_format_problems(qml)]
    assert not problems, "Text without textFormat: Text.PlainText:\n" + "\n".join(problems)


@per_folder
def test_bar_widget_never_sizes_itself_off_its_parent(folder: Path) -> None:
    """Omarchy's ModuleSlot takes its height from the widget's implicit size, so
    `implicitHeight: parent.height` is a binding loop QML drops: zero height, nothing logged."""
    offenders = [
        f"{qml.relative_to(REPO_ROOT)}: {ln.strip()}"
        for qml in sorted(folder.rglob("*.qml"))
        for ln in qml_code(qml).splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", ln) and "parent" in ln
    ]
    assert not offenders, "implicit size off `parent`:\n" + "\n".join(offenders)


@per_folder
def test_plugin_qml_parses(folder: Path) -> None:
    """A QML syntax error is an empty bar slot with nothing in any log. `qmllint --bare`
    parses without the module imports."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    for qml in sorted(folder.rglob("*.qml")):
        proc = subprocess.run([qmllint, "--bare", str(qml)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{qml}: {proc.stderr}"


def test_widgets_read_only_what_the_plugin_facades_expose() -> None:
    """Every `bar.<x>` / `bar.shell.<x>` in a shipped widget is a facade member. Never a
    skip: where Omarchy is absent the pinned lists stand in."""
    bar_api = OMARCHY_SHELL / "Ui/PluginBarApi.qml"
    shell_api = OMARCHY_SHELL / "services/PluginShellApi.qml"
    allowed = set(PLUGIN_BAR_API) | set(PLUGIN_SHELL_API)
    if bar_api.is_file() and shell_api.is_file():
        declared = lambda f: {m for m in DECLARES_RE.findall(f.read_text()) if m[0] != "_"}  # noqa: E731
        assert declared(bar_api) == set(PLUGIN_BAR_API)
        assert declared(shell_api) == set(PLUGIN_SHELL_API)
    seen = set()
    for qml in sorted(p for folder in FOLDERS for p in folder.rglob("*.qml")):
        for member in MEMBER_RE.findall(OWNER_RE.sub("", qml_code(qml))):
            assert member in allowed, f"{qml}: bar.{member} is not on the facades"
            seen.add(member)
    assert {"serviceFor", "updateEntryInline"} <= seen, "the scan matched nothing it should"


@per_folder
@pytest.mark.skipif(not (OMARCHY / "bin/omarchy-plugin-validate").is_file(), reason=NEEDS_OMARCHY)
def test_the_real_validator_accepts_the_folder_through_a_symlink(
    folder: Path, tmp_path: Path
) -> None:
    """What every install puts in ~/.config/omarchy/plugins/ is a symlink, and the validator
    refuses one INSIDE a plugin folder — hence the trailing slash, which makes its own `find`
    descend the link instead of printing it (bin/omarchy-plugin-validate:115)."""
    validate = OMARCHY / "bin/omarchy-plugin-validate"
    (link := tmp_path / "p").symlink_to(folder)

    def run(path: str) -> subprocess.CompletedProcess:
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
        return subprocess.run(
            ["bash", str(validate), path], capture_output=True, text=True, timeout=30, env=env
        )

    passed, bare = run(f"{link}/"), run(str(link))
    assert passed.returncode == 0, passed.stderr
    assert bare.returncode != 0 and "symlink" in bare.stderr


# -- the shared install mechanism, once per plugin folder -------------------
# modules/bar-plugin.sh, which the four modules/bar-*/install source: what each of them
# used to assert for itself, here with the strongest of the four assertion sets.


@dataclass(frozen=True)
class Plugin:
    """One bar module read off its own files — the id its manifest claims, the id it was
    cloned from (a widget of its own: none), and the two paths its install may create."""

    box: Box
    module: str
    folder: Path
    install: Path
    id: str
    stock: str
    link: Path
    marker: Path
    sets_a_bar_key: bool

    def run(self, *args: str) -> subprocess.CompletedProcess:
        proc = self.box.run(self.install, *args)
        assert proc.returncode == 0, proc.stderr
        return proc


@pytest.fixture(params=FOLDERS, ids=lambda f: f.parent.name)
def plugin(request: pytest.FixtureRequest, box: Box) -> Plugin:
    install = request.param.parent / "install"
    text = install.read_text()
    manifest = json.loads((request.param / "manifest.json").read_text())
    marker = re.search(r"^marker=\S*/([a-z-]+-applied)$", text, re.M)
    assert marker, f"{install}: no marker= line to derive the set-once marker from"
    return Plugin(
        box=box,
        module=request.param.parent.name,
        folder=request.param,
        install=install,
        id=manifest["id"],
        stock=manifest.get("omarchy", {}).get("clonedFrom", ""),
        link=box.home / ".config/omarchy/plugins" / manifest["id"],
        marker=box.home / ".local/state/hyprconf" / marker.group(1),
        sets_a_bar_key="omarchy-bar set" in text,
    )


def test_install_links_the_folder_rescans_it_and_enables_it_once(plugin: Plugin) -> None:
    """One rescan, one enable, and no placement on it: a --section would splice a clonedFrom
    copy straight back out of the stock widget's slot (PluginRegistry.qml:545-546)."""
    box = plugin.box
    bar_shell(box)
    plugin.run()
    assert plugin.link.readlink() == plugin.folder
    assert box.calls_of("omarchy-shell") == [["omarchy-shell", "shell", "rescanPlugins"]]
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", plugin.id]]
    assert plugin.marker.is_file() and "sudo" not in box.commands
    # A bar key is a user choice: only a module whose install sets one may call for it.
    keyed = [c[2] for c in box.calls_of("omarchy-bar")]
    assert keyed == ([plugin.id] if plugin.sets_a_bar_key else [])


def test_a_second_run_writes_nothing_and_enables_nothing(plugin: Plugin) -> None:
    """The post-update hook re-runs every module after every omarchy-update, and a widget
    never goes back on a bar the user took it off (rule 5)."""
    box = plugin.box
    bar_shell(box)
    plugin.run()
    before = box.snapshot()
    box.reset()
    plugin.run()
    assert box.snapshot() == before
    assert box.commands == ["omarchy-shell"]  # the rescan, and no mutating command at all


def test_an_omarchy_plugin_add_checkout_of_the_same_id_is_left_to_omarchy(plugin: Plugin) -> None:
    """`omarchy plugin update` fast-forwards it (bin/omarchy-plugin-update:111-112): it is
    the user's checkout, not ours to link over."""
    (plugin.link / ".git").mkdir(parents=True)
    proc = plugin.run()
    assert "omarchy plugin update" in proc.stdout
    assert not plugin.link.is_symlink() and not plugin.marker.exists()
    assert plugin.box.commands == []


def test_undo_beside_that_checkout_drops_only_this_modules_marker(plugin: Plugin) -> None:
    """`hyprconf --undo` runs every module's undo, so a same-id checkout is reached without
    being named: nothing of it is disabled, reformatted or unlinked."""
    box = plugin.box
    (plugin.link / ".git").mkdir(parents=True)
    plugin.marker.parent.mkdir(parents=True)
    plugin.marker.touch()
    assert box.undo(plugin.module).returncode == 0
    assert box.commands == [] and not plugin.marker.exists()
    assert (plugin.link / ".git").is_dir() and not plugin.link.is_symlink()


def test_a_real_folder_is_moved_aside_once_and_a_stale_link_repaired(plugin: Plugin) -> None:
    """Moved to `.<id>.bak.<timestamp>`, what omarchy-plugin-remove does with a folder it
    did not clone (bin/omarchy-plugin-remove:106) — never deleted, and never twice."""
    box = plugin.box
    bar_shell(box)
    plugin.link.mkdir(parents=True)
    (plugin.link / "manifest.json").write_text('{"id": "the copy from before"}\n')
    plugin.run()
    (backup,) = plugin.link.parent.glob(f".{plugin.id}.bak.*")
    assert re.fullmatch(rf"\.{re.escape(plugin.id)}\.bak\.\d{{14}}", backup.name)
    assert (backup / "manifest.json").read_text() == '{"id": "the copy from before"}\n'
    assert plugin.link.readlink() == plugin.folder
    plugin.link.unlink()
    plugin.link.symlink_to(box.tmp / "somewhere-else")
    plugin.run()
    assert plugin.link.readlink() == plugin.folder
    assert list(plugin.link.parent.glob(f".{plugin.id}.bak.*")) == [backup]


def test_no_shell_answering_leaves_the_enable_for_the_next_run(plugin: Plugin) -> None:
    """The link still lands and the run still succeeds — it must not fail the module loop —
    and nothing of the user's bar is touched. `omarchy-plugin-list` exits 1 with no shell
    (bin/omarchy-shell:14-17), which is what ends the discovery wait after one poll."""
    box = plugin.box
    path = bar_shell(box)
    before = path.read_bytes()
    box.stub("omarchy-plugin-list", "exit 1\n")
    box.stub("omarchy-plugin-enable", "exit 1\n")
    proc = plugin.run()
    assert "next run" in proc.stdout
    assert plugin.link.is_symlink() and not plugin.marker.exists()
    assert box.commands.count("omarchy-plugin-list") == 1
    assert "omarchy-bar" not in box.commands and path.read_bytes() == before
    box.stub("omarchy-plugin-list", PLUGIN_LIST)
    box.stub("omarchy-plugin-enable", PLUGIN_ENABLE)
    plugin.run()
    assert box.calls_of("omarchy-plugin-enable")[-1] == ["omarchy-plugin-enable", plugin.id]
    assert plugin.marker.is_file()


def test_undo_disables_it_first_then_takes_the_link_and_the_marker_away(plugin: Plugin) -> None:
    """Disabled while still installed: the clonedFrom entry is what hands the slot back to
    the stock widget (PluginRegistry.qml:555 -> restoreCloneSource:441)."""
    box = plugin.box
    bar_shell(box)
    plugin.run()
    box.reset()
    assert box.undo(plugin.module).returncode == 0
    assert box.calls[0] == f"omarchy-plugin-disable {plugin.id}"
    assert box.calls.count(f"omarchy-plugin-disable {plugin.id}") == 1
    assert not plugin.link.exists(follow_symlinks=False) and not plugin.marker.exists()
    assert (plugin.folder / "manifest.json").is_file()  # the payload it pointed at is untouched
    assert box.calls_of("omarchy-shell") == [["omarchy-shell", "shell", "rescanPlugins"]]


def test_undo_with_no_shell_answering_hands_the_slot_back_in_the_file(plugin: Plugin) -> None:
    """With nothing answering there is no in-memory copy to take an edit back, so the swap
    the disable would do is done in shell.json itself — a layout entry naming a plugin that
    is gone is a 0-width slot next session (Bar.qml:1795, :1814)."""
    box = plugin.box
    path = bar_shell(box, layout=[{"id": plugin.id}])
    box.stub("omarchy-plugin-disable", "exit 1\n")
    assert box.undo(plugin.module).returncode == 0
    # A centre entry is a bare id or an object with one (bin/omarchy-bar:178).
    centre = json.loads(path.read_text())["bar"]["layout"]["center"]
    assert [e["id"] if isinstance(e, dict) else e for e in centre] == (
        [plugin.stock] if plugin.stock else []
    )


def test_undo_on_a_box_that_never_installed_writes_nothing(plugin: Plugin) -> None:
    assert plugin.box.undo(plugin.module).returncode == 0
    assert plugin.box.files() == set()


def test_undo_leaves_a_folder_that_is_not_its_own_link_whole(plugin: Plugin) -> None:
    """`rm -f` on a directory fails, which would take the whole undo down with it."""
    plugin.link.mkdir(parents=True)
    (plugin.link / "manifest.json").write_text("{}\n")
    assert plugin.box.undo(plugin.module).returncode == 0
    assert (plugin.link / "manifest.json").read_text() == "{}\n"
