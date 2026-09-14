"""Tests for modules/bar-clock — Omarchy's clock widget, ticking seconds.

The contract: the plugin folder is LINKED into ~/.config/omarchy/plugins, the
shell is asked to rescan every run, the widget is enabled and formatted ONCE
behind a marker, the bar's centre anchor follows the swap once and is repaired
whenever it names nothing, and `install undo` puts the stock format, the stock
anchor and a clean plugins directory back.

HERMETIC: the `box` fixture (conftest.py) — tmp HOME, tmp $OMARCHY_PATH, and
every omarchy-* command a recording fake. `shell()` below replaces four of
those fakes with a small model of the live shell: the plugin list answers from
the box's plugins directory, enable/disable move the bar entry between the
clone and the id it was cloned from (PluginRegistry.qml:441 restoreCloneSource
carries the entry, format included), and `omarchy-bar set` writes the key onto
the entry. Three tests need the installed Omarchy and skip without it — the
real `omarchy-plugin-validate` run, the parity diff against the stock widget
and the Model.js subset diff (AGENTS › Gates and CI budgets for every skip).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
PLUGIN = MODULE / "plugin"
ID = "hyprconf.clock"
STOCK = "omarchy.clock"
FORMAT = "hh:mm:ss AP"
STOCK_FORMAT = "dddd HH:mm"

# The installed Omarchy, for the two tests that need the real thing. Not
# box.omarchy: that tree is a fixture cut to what the module reads.
OMARCHY = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
STOCK_CLOCK = OMARCHY / "shell/plugins/panels/clock"
VALIDATE = OMARCHY / "bin/omarchy-plugin-validate"

# ---- the shell model -------------------------------------------------------

# Every layout entry is a bare id or an object with one (bin/omarchy-bar:178).
ENTRY_ID = 'if type == "object" then .id else . end'
LIST = """
dir="$HOME/.config/omarchy/plugins"
ids=()
for sub in "$dir"/*/; do
    [[ -f "$sub/manifest.json" ]] || continue
    ids+=("$(jq -r .id "$sub/manifest.json")")
done
jq -n --args '[$ARGS.positional[] | {id: .}]' "${ids[@]}"
"""
# enable swaps the clone into the slot of the id its manifest was cloned from;
# disable hands the whole entry back, which is why the format survives it.
SWAP = """
json="$HOME/.config/omarchy/shell.json"
[[ -f $json ]] || exit 1
src=$(jq -r '.omarchy.clonedFrom // empty' \
    "$HOME/.config/omarchy/plugins/$1/manifest.json" 2>/dev/null) || exit 1
jq --arg from "%s" --arg to "%s" '
    .bar.layout |= with_entries(.value |= map(
        if (ENTRY_ID) == $from
        then (if type == "object" then .id = $to else { id: $to } end)
        else . end))' "$json" > "$json.t" && mv "$json.t" "$json"
"""
BAR_SET = """
[[ ${1:-} == set ]] || exit 0
json="$HOME/.config/omarchy/shell.json"
[[ -f $json ]] || exit 1
jq --arg id "$2" --arg k "$3" --arg v "$4" '
    .bar.layout |= with_entries(.value |= map(
        if (ENTRY_ID) == $id
        then (if type == "object" then . else { id: . } end) + { ($k): $v }
        else . end))' "$json" > "$json.t" && mv "$json.t" "$json"
"""


# The same write, landing on a LATER event-loop turn: the shell answers the
# IPC at once and persists shell.json afterwards (shell.qml:109-113
# persistShellConfig, then a FileView setText). The snapshot is taken when the
# call comes in, so a run that edits the anchor without waiting for this write
# has its edit overwritten by the pre-edit copy 0.2 s later.
BAR_SET_LATE = """
[[ ${1:-} == set ]] || exit 0
json="$HOME/.config/omarchy/shell.json"
[[ -f $json ]] || exit 1
snap=$(jq --arg id "$2" --arg k "$3" --arg v "$4" '
    .bar.layout |= with_entries(.value |= map(
        if (ENTRY_ID) == $id
        then (if type == "object" then . else { id: . } end) + { ($k): $v }
        else . end))' "$json")
( sleep 0.2; printf '%s' "$snap" > "$json" ) &
exit 0
"""


def shell(box: Box, anchor: str = STOCK, layout: list | None = None) -> Path:
    """Give the box a ~/.config/omarchy/shell.json and the four fakes that
    model the running shell. Returns the shell.json path."""
    json_path = box.home / ".config/omarchy/shell.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "version": 1,
                "bar": {
                    "centerAnchor": anchor,
                    "layout": {
                        "left": ["omarchy.menu"],
                        "center": layout
                        if layout is not None
                        else [{"id": STOCK, "format": STOCK_FORMAT}],
                        "right": [],
                    },
                },
            },
            indent=2,
        )
        + "\n"
    )
    box.stub("omarchy-plugin-list", LIST)
    box.stub("omarchy-plugin-enable", (SWAP % ("$src", "$1")).replace("ENTRY_ID", ENTRY_ID))
    box.stub("omarchy-plugin-disable", (SWAP % ("$1", "$src")).replace("ENTRY_ID", ENTRY_ID))
    box.stub("omarchy-bar", BAR_SET.replace("ENTRY_ID", ENTRY_ID))
    return json_path


def bar(json_path: Path) -> list[dict]:
    """The centre section's entries, as objects."""
    entries = json.loads(json_path.read_text())["bar"]["layout"]["center"]
    return [e if isinstance(e, dict) else {"id": e} for e in entries]


def anchor_of(json_path: Path) -> str:
    return json.loads(json_path.read_text())["bar"]["centerAnchor"]


def files(home: Path) -> dict[str, str]:
    """Every path under HOME with its content — a link as its target, so a
    second run that relinked or rewrote anything shows up."""
    out: dict[str, str] = {}
    for root, dirs, names in os.walk(home):  # never follows a symlink
        for name in sorted(dirs + names):
            path = Path(root) / name
            rel = str(path.relative_to(home))
            if path.is_symlink():
                out[rel] = "-> " + os.readlink(path)
            elif path.is_file():
                out[rel] = path.read_text()
            else:
                out[rel] = "<dir>"
    return out


def link_of(box: Box) -> Path:
    return box.home / ".config/omarchy/plugins" / ID


def marker_of(box: Box) -> Path:
    return box.home / ".local/state/hyprconf/clock-applied"


# ---- installing ------------------------------------------------------------


def test_links_the_plugin_and_enables_it_once_with_the_format_and_the_anchor(box: Box) -> None:
    json_path = shell(box)
    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert link_of(box).is_symlink()
    assert os.readlink(link_of(box)) == str(PLUGIN)
    assert marker_of(box).exists()
    assert "omarchy-shell" in box.commands  # the watcher does not follow a link
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    assert box.calls_of("omarchy-bar") == [["omarchy-bar", "set", ID, "format", FORMAT]]
    assert bar(json_path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(json_path) == ID


def test_a_second_run_enables_nothing_and_writes_nothing(box: Box) -> None:
    json_path = shell(box)
    box.run(INSTALL)
    before = files(box.home)
    box.reset()

    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert files(box.home) == before
    assert "omarchy-plugin-enable" not in box.commands
    assert "omarchy-bar" not in box.commands
    assert anchor_of(json_path) == ID


def test_without_a_shell_it_links_and_leaves_the_enable_to_the_next_run(box: Box) -> None:
    json_path = shell(box)
    box.stub("omarchy-plugin-list", "exit 1\n")  # omarchy-shell answers nothing
    box.stub("omarchy-plugin-enable", "exit 1\n")

    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert link_of(box).is_symlink()
    assert not marker_of(box).exists()
    assert "next run" in result.stdout
    assert "omarchy-bar" not in box.commands
    assert anchor_of(json_path) == STOCK
    # one poll's worth: with no shell to ask there is nothing to wait for
    assert len(box.calls_of("omarchy-plugin-list")) == 1


def test_a_home_with_no_shell_json_yet_is_fine(box: Box) -> None:
    """Nothing has written ~/.config/omarchy/shell.json yet: the shell creates
    it on its first persist, which here is the enable."""
    json_path = shell(box)
    json_path.unlink()
    box.stub(
        "omarchy-plugin-enable",
        f'printf \'{{"version":1,"bar":{{"centerAnchor":"{STOCK}",'
        f'"layout":{{"left":[],"center":[{{"id":"{ID}"}}],"right":[]}}}}}}\\n\''
        ' > "$HOME/.config/omarchy/shell.json"\n',
    )

    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert marker_of(box).exists()
    assert bar(json_path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(json_path) == ID


def test_an_omarchy_plugin_add_checkout_is_left_alone(box: Box) -> None:
    shell(box)
    (link_of(box) / ".git").mkdir(parents=True)

    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert "omarchy plugin update" in result.stdout
    assert not link_of(box).is_symlink()
    assert not marker_of(box).exists()
    assert box.commands == []


def test_a_real_folder_is_moved_aside_once(box: Box) -> None:
    shell(box)
    plugins = link_of(box).parent
    link_of(box).mkdir(parents=True)
    (link_of(box) / "manifest.json").write_text('{"id": "hyprconf.clock"}\n')

    box.run(INSTALL)
    backups = sorted(p.name for p in plugins.iterdir() if p.name.startswith(f".{ID}.bak."))

    assert len(backups) == 1
    assert re.fullmatch(rf"\.{re.escape(ID)}\.bak\.\d{{14}}", backups[0])
    assert (plugins / backups[0] / "manifest.json").exists()
    assert os.readlink(link_of(box)) == str(PLUGIN)

    box.run(INSTALL)  # the link is ours now, so nothing is moved a second time
    assert [p.name for p in plugins.iterdir() if p.name.startswith(f".{ID}.bak.")] == backups


# ---- the centre anchor -----------------------------------------------------


def test_an_anchor_that_names_nothing_is_repaired_after_the_marker(box: Box) -> None:
    """A clone removed long after the install leaves bar.centerAnchor naming
    an id that exists nowhere, and the centre section then centres the whole
    group (Bar.qml:1538 hasAnchor). Not a choice, so not behind the marker."""
    json_path = shell(box, anchor="testuser.clock", layout=[{"id": ID, "format": FORMAT}])
    marker_of(box).parent.mkdir(parents=True)
    marker_of(box).touch()

    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert anchor_of(json_path) == ID
    assert "omarchy-plugin-enable" not in box.commands
    assert "named nothing" in result.stdout


def test_an_anchor_the_user_chose_is_left_alone(box: Box) -> None:
    """Two ways an anchor is still the user's: it names a widget on the bar,
    or a plugin they merely disabled. Only an id that is on neither is stale."""
    json_path = shell(box, anchor="omarchy.menu", layout=[{"id": ID, "format": FORMAT}])
    marker_of(box).parent.mkdir(parents=True)
    marker_of(box).touch()
    box.run(INSTALL)
    assert anchor_of(json_path) == "omarchy.menu"

    disabled = link_of(box).parent / "someone.weather"
    disabled.mkdir(parents=True)
    (disabled / "manifest.json").write_text('{"id": "someone.weather"}\n')
    json_path.write_text(json_path.read_text().replace('"omarchy.menu"', '"someone.weather"', 1))

    box.run(INSTALL)

    assert anchor_of(json_path) == "someone.weather"


def test_the_anchor_is_not_moved_onto_a_clock_the_bar_does_not_carry(box: Box) -> None:
    """Whether the user disabled our clock or an enable never landed, the bar
    has no hyprconf.clock — so a stale anchor is left stale rather than pointed
    at a widget that is not there."""
    json_path = shell(box, anchor="testuser.clock")
    marker_of(box).parent.mkdir(parents=True)
    marker_of(box).touch()

    box.run(INSTALL)
    assert anchor_of(json_path) == "testuser.clock"

    marker_of(box).unlink()
    box.stub("omarchy-plugin-enable", "exit 1\n")

    box.run(INSTALL)

    assert anchor_of(json_path) == "testuser.clock"
    assert not marker_of(box).exists()


def test_an_anchor_edit_that_cannot_be_written_warns_and_leaves_no_temp_file(box: Box) -> None:
    """A cosmetic step must not take the run down, nor report success it did
    not have: the write goes through an if, not a `&& mv` tail."""
    json_path = shell(box, anchor="testuser.clock", layout=[{"id": ID, "format": FORMAT}])
    marker_of(box).parent.mkdir(parents=True)
    marker_of(box).touch()
    blocked = Path(f"{json_path}.tmp")
    blocked.mkdir()  # nothing can be written there

    result = box.run(INSTALL)

    assert result.returncode == 0
    assert "could not set bar.centerAnchor" in result.stderr
    assert anchor_of(json_path) == "testuser.clock"
    assert blocked.is_dir() and not any(blocked.iterdir())


def test_the_anchor_edit_waits_for_the_shells_own_write_to_land(box: Box) -> None:
    """The anchor edit is a read-modify-write on a file the SHELL owns: it
    answers `omarchy bar set` at once and persists shell.json on a later
    event-loop turn. Without settled() the edit reads the pre-set copy and the
    shell's pending write takes it straight back — so this box answers
    immediately and writes 0.2 s later, and the anchor has to survive it."""
    json_path = shell(box)
    box.stub("omarchy-bar", BAR_SET_LATE.replace("ENTRY_ID", ENTRY_ID))

    result = box.run(INSTALL)

    assert result.returncode == 0, result.stderr
    assert bar(json_path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(json_path) == ID


# ---- undo ------------------------------------------------------------------


def test_undo_restores_the_stock_format_the_anchor_and_the_plugins_directory(box: Box) -> None:
    json_path = shell(box)
    box.run(INSTALL)
    box.reset()

    result = box.undo("bar-clock")

    assert result.returncode == 0, result.stderr
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", ID]]
    assert box.calls_of("omarchy-bar") == [["omarchy-bar", "set", STOCK, "format", STOCK_FORMAT]]
    assert bar(json_path) == [{"id": STOCK, "format": STOCK_FORMAT}]
    assert anchor_of(json_path) == STOCK
    assert not link_of(box).exists()
    assert not marker_of(box).exists()
    assert "omarchy-shell" in box.commands


def test_undo_without_a_shell_still_unlinks(box: Box) -> None:
    shell(box)
    box.run(INSTALL)
    box.stub("omarchy-plugin-disable", "exit 1\n")
    box.reset()

    result = box.undo("bar-clock")

    assert result.returncode == 0, result.stderr
    assert not link_of(box).exists()
    assert not marker_of(box).exists()
    assert "omarchy-bar" not in box.commands


def test_undo_on_a_box_that_never_installed_is_a_no_op(box: Box) -> None:
    shell(box)
    before = files(box.home)

    result = box.undo("bar-clock")

    assert result.returncode == 0, result.stderr
    assert files(box.home) == before


# ---- the shipped folder ----------------------------------------------------


def test_the_manifest_claims_the_stock_clock_slot() -> None:
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID
    assert manifest["omarchy"] == {"clonedFrom": STOCK}
    assert manifest["entryPoints"] == {"barWidget": "BarWidget.qml"}
    # Nothing reads the value (omarchy-plugin-update is a fast-forward, the
    # validator checks presence only) and Omarchy's own plugins never move
    # theirs off 1.0.0 — so it is frozen, not a discipline.
    assert manifest["version"] == "1.0.0"


def test_the_widget_carries_no_panel_of_its_own() -> None:
    """Delta 2: the calendar comes from the running Omarchy, so a release that
    changes the panel needs nothing here."""
    assert not (PLUGIN / "Panel.qml").exists()
    widget = (PLUGIN / "BarWidget.qml").read_text()
    assert 'Quickshell.env("OMARCHY_PATH")' in widget
    assert 'import "Model.js" as Model' in widget


def test_the_widget_qml_parses() -> None:
    """A QML syntax error is an empty bar slot with nothing in any log.
    `qmllint --bare` parses without resolving the imports: exit 0 with import
    warnings on a good file, non-zero on a broken one."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    for qml in sorted(PLUGIN.rglob("*.qml")):
        proc = subprocess.run([qmllint, "--bare", str(qml)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{qml.name}: {proc.stderr}"


def test_the_widget_never_sizes_itself_off_its_parent() -> None:
    """Omarchy's ModuleSlot takes its height from the widget's implicit size,
    so `implicitHeight: parent.height` closes a binding loop — QML drops the
    binding, and the widget is a zero-size gap in the bar with nothing logged
    at any verbosity."""
    offenders = [
        line.strip()
        for qml in sorted(PLUGIN.rglob("*.qml"))
        for line in qml.read_text().splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]
    assert not offenders, "implicit size must not read `parent`:\n" + "\n".join(offenders)


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason="needs the installed Omarchy")
def test_the_widget_tracks_omarchys_stock_clock() -> None:
    """BarWidget.qml is the stock file plus this plugin's header and exactly
    the three deltas that header names. Red on an Omarchy release that changes
    the clock — which is the signal to refresh the copy."""
    ours = (PLUGIN / "BarWidget.qml").read_text().splitlines()
    body = ours[next(n for n, ln in enumerate(ours) if ln.startswith("import ")) :]
    stock = (STOCK_CLOCK / "BarWidget.qml").read_text().splitlines()
    changed = [
        ln
        for ln in difflib.unified_diff(stock, body, n=0, lineterm="")
        if ln[:1] in "+-" and not ln.startswith(("---", "+++"))
    ]
    assert changed == [
        '+    if ("moduleName" in target) target.moduleName = root.moduleName',
        "+  onModuleNameChanged: injectPanel()",
        "-    precision: SystemClock.Minutes",
        "+    precision: SystemClock.Seconds",
        '-    source: Qt.resolvedUrl("Panel.qml")',
        '+    source: "file://" + Quickshell.env("OMARCHY_PATH")'
        ' + "/shell/plugins/panels/clock/Panel.qml"',
    ]


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason="needs the installed Omarchy")
def test_model_js_is_omarchys_label_math_and_only_that() -> None:
    """Model.js is the subset of Omarchy's that BarWidget.qml calls, verbatim.
    The calendar half is not here: the panel is loaded from Omarchy's tree by
    absolute URL, and a QML document resolves `import "Model.js"` against its
    own directory, so the panel reads Omarchy's copy (verified live under
    Qt 6.11). Each kept declaration is compared to the stock one, so an
    Omarchy release that changes the label math turns this red."""
    kept = [
        "MS_PER_DAY",
        "CLOCK_FORMATS",
        "VERTICAL_CLOCK_FORMATS",
        "clockFormats",
        "clockFormatRing",
        "nextClockFormat",
        "isoWeekLiteral",
        "pad2",
        "isoWeek",
    ]
    ours = declarations((PLUGIN / "Model.js").read_text())
    stock = declarations((STOCK_CLOCK / "Model.js").read_text())
    assert sorted(ours) == sorted(kept)
    for name in kept:
        assert ours[name] == stock[name], f"{name} has drifted from Omarchy's"
    # Every name the widget reaches for is one of them, and the calendar's
    # entry points are gone with the math they served.
    widget = (PLUGIN / "BarWidget.qml").read_text()
    assert set(re.findall(r"\bModel\.([A-Za-z0-9_]+)\(", widget)) <= set(kept)
    assert "monthGrid" not in ours and "monthGrid" in stock


def declarations(source: str) -> dict[str, str]:
    """Every top-level `var`/`function` in a Model.js, name -> its text: from
    the declaration to the comment block introducing the next one, which
    belongs to that one."""
    starts = [
        (m.start(), m.group(1))
        for m in re.finditer(r"^(?:var|function)\s+([A-Za-z0-9_]+)", source, re.M)
    ]
    out = {}
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(source)
        lines = source[pos:end].splitlines()
        while lines and (not lines[-1].strip() or lines[-1].startswith("//")):
            lines.pop()
        out[name] = "\n".join(lines)
    return out


@pytest.mark.skipif(not VALIDATE.exists(), reason="needs the installed Omarchy")
def test_the_installed_link_passes_omarchy_plugin_validate(box: Box) -> None:
    """The real validator, on the path the module installs — with the trailing
    slash it needs: without one its own `find … -type l` prints the link
    (bin/omarchy-plugin-validate:115) and it refuses the folder."""
    shell(box)
    box.run(INSTALL)

    ok = subprocess.run(["bash", str(VALIDATE), f"{link_of(box)}/"], capture_output=True, text=True)
    bare = subprocess.run(
        ["bash", str(VALIDATE), str(link_of(box))], capture_output=True, text=True
    )

    assert ok.returncode == 0, ok.stderr
    assert bare.returncode == 1 and "symlink" in bare.stderr
