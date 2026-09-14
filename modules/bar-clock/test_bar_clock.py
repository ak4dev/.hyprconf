"""modules/bar-clock: the plugin folder is LINKED and rescanned every run, enabled
and formatted ONCE behind a marker, the centre anchor follows the swap and is
repaired when it names nothing, and `install undo` puts the stock back."""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import Box

INSTALL = Path(__file__).parent / "install"
PLUGIN = Path(__file__).parent / "plugin"
ID = "hyprconf.clock"
STOCK = "omarchy.clock"
FORMAT = "hh:mm:ss AP"
STOCK_FORMAT = "dddd HH:mm"
LINK = f".config/omarchy/plugins/{ID}"
MARKER = ".local/state/hyprconf/clock-applied"
# The installed Omarchy, for the pins that need the real thing — not
# box.omarchy, which is a fixture cut to what the module reads.
OMARCHY = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
STOCK_CLOCK = OMARCHY / "shell/plugins/panels/clock"
VALIDATE = OMARCHY / "bin/omarchy-plugin-validate"

# A model of the running shell. Every layout entry is a bare id or an object
# with one (bin/omarchy-bar:178); enable swaps the clone into the slot of the id
# its manifest was cloned from, and disable hands the whole entry back, format
# included (PluginRegistry.qml:441).
EDIT = """
json="$HOME/.config/omarchy/shell.json"
[[ -f $json ]] || exit 1
%s
jq %s '
    .bar.layout |= with_entries(.value |= map(
        if (if type == "object" then .id else . end) == $a then %s
        else . end))' "$json" > "$json.t" && mv "$json.t" "$json"
"""
CLONED_FROM = """src=$(jq -r '.omarchy.clonedFrom // empty' \
    "$HOME/.config/omarchy/plugins/$1/manifest.json" 2>/dev/null) || exit 1"""
RENAME = '(if type == "object" then .id = $b else { id: $b } end)'
ENABLE = EDIT % (CLONED_FROM, '--arg a "$src" --arg b "$1"', RENAME)
DISABLE = EDIT % (CLONED_FROM, '--arg a "$1" --arg b "$src"', RENAME)
BAR_SET = EDIT % (
    "[[ ${1:-} == set ]] || exit 1",
    '--arg a "$2" --arg k "$3" --arg v "$4"',
    '(if type == "object" then . else { id: . } end) + { ($k): $v }',
)
# The same write, persisted on a LATER event-loop turn as the shell's is
# (shell.qml:109-113 persistShellConfig, then a FileView setText): an anchor
# edit that does not wait for it is taken straight back 0.2 s later.
BAR_SET_LATE = BAR_SET.replace('&& mv "$json.t"', '&& { ( sleep 0.2; mv "$json.t"')[:-1] + ") & }\n"
LIST = """
cd "$HOME/.config/omarchy/plugins" 2>/dev/null || exit 1
jq -n --args '[$ARGS.positional[] | { id: rtrimstr("/") }]' -- */
"""


def shell(box: Box, anchor: str = STOCK, layout: list | None = None) -> Path:
    """The box's ~/.config/omarchy/shell.json plus the four fakes that model the shell."""
    path = box.home / ".config/omarchy/shell.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    center = [{"id": STOCK, "format": STOCK_FORMAT}] if layout is None else layout
    layouts = {"left": ["omarchy.menu"], "center": center, "right": []}
    path.write_text(json.dumps({"bar": {"centerAnchor": anchor, "layout": layouts}}, indent=2))
    box.stub("omarchy-plugin-list", LIST)
    box.stub("omarchy-plugin-enable", ENABLE)
    box.stub("omarchy-plugin-disable", DISABLE)
    box.stub("omarchy-bar", BAR_SET)
    return path


def bar(path: Path) -> list[dict]:
    """The centre section's entries, as objects."""
    center = json.loads(path.read_text())["bar"]["layout"]["center"]
    return [e if isinstance(e, dict) else {"id": e} for e in center]


def anchor_of(path: Path) -> str:
    return json.loads(path.read_text())["bar"]["centerAnchor"]


def snapshot(home: Path) -> dict[str, str]:
    """Every path under HOME with its content, a link as its target."""
    out = {}
    for p in home.rglob("*"):  # never descends a symlink (3.13+)
        out[str(p.relative_to(home))] = (
            os.readlink(p) if p.is_symlink() else p.read_text() if p.is_file() else "<dir>"
        )
    return out


def test_install_links_the_plugin_and_enables_it_once_with_the_format_and_anchor(box: Box) -> None:
    path = shell(box)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert os.readlink(box.home / LINK) == str(PLUGIN)
    assert (box.home / MARKER).exists()
    assert "omarchy-shell" in box.commands  # the watcher does not follow a link
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    assert box.calls_of("omarchy-bar") == [["omarchy-bar", "set", ID, "format", FORMAT]]
    assert bar(path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(path) == ID


def test_a_second_run_writes_nothing_and_calls_nothing_that_mutates(box: Box) -> None:
    shell(box)
    box.run(INSTALL)
    before = snapshot(box.home)
    box.reset()
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert snapshot(box.home) == before
    assert box.commands == ["omarchy-shell"]  # the rescan, and nothing else


def test_without_a_shell_it_links_and_leaves_the_enable_to_the_next_run(box: Box) -> None:
    path = shell(box)
    box.stub("omarchy-plugin-list", "exit 1\n")  # omarchy-shell answers nothing
    box.stub("omarchy-plugin-enable", "exit 1\n")
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert (box.home / LINK).is_symlink()
    assert not (box.home / MARKER).exists()
    assert "next run" in result.stdout
    assert "omarchy-bar" not in box.commands
    assert anchor_of(path) == STOCK
    # one poll's worth: with no shell to ask there is nothing to wait for
    assert len(box.calls_of("omarchy-plugin-list")) == 1


def test_an_omarchy_plugin_add_checkout_is_left_alone(box: Box) -> None:
    shell(box)
    (box.home / LINK / ".git").mkdir(parents=True)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert "omarchy plugin update" in result.stdout
    assert not (box.home / LINK).is_symlink()
    assert not (box.home / MARKER).exists()
    assert box.commands == []


def test_a_real_folder_is_moved_aside_once(box: Box) -> None:
    shell(box)
    plugins = (box.home / LINK).parent
    (box.home / LINK).mkdir(parents=True)
    (box.home / LINK / "manifest.json").write_text('{"id": "hyprconf.clock"}\n')
    box.run(INSTALL)
    backups = sorted(p.name for p in plugins.iterdir() if p.name.startswith(f".{ID}.bak."))
    assert len(backups) == 1 and re.fullmatch(rf"\.{re.escape(ID)}\.bak\.\d{{14}}", backups[0])
    assert (plugins / backups[0] / "manifest.json").exists()
    assert os.readlink(box.home / LINK) == str(PLUGIN)
    box.run(INSTALL)  # the link is ours now, so nothing is moved a second time
    assert [p.name for p in plugins.iterdir() if p.name.startswith(f".{ID}.bak.")] == backups


@pytest.mark.parametrize(
    ("anchor", "layout", "expected", "blocked"),
    [
        # the swap: the stock id the clone took the slot from
        (STOCK, [{"id": ID}], ID, False),
        # a clone removed long after the install — on no section and on no
        # installed plugin, so the section centres the whole group instead
        # (Bar.qml:1538 hasAnchor). Not a choice, so not behind the marker.
        ("testuser.clock", [{"id": ID}], ID, False),
        # the same repair with the write blocked: a cosmetic step must not take
        # the run down, nor report success it did not have
        ("testuser.clock", [{"id": ID}], "testuser.clock", True),
        # still the user's: a widget the bar carries ...
        ("omarchy.menu", [{"id": ID}], "omarchy.menu", False),
        # ... or a plugin they merely disabled (someone.weather, installed below)
        ("someone.weather", [{"id": ID}], "someone.weather", False),
        # our clock is on no section, so there is nothing to point at
        ("testuser.clock", [{"id": STOCK}], "testuser.clock", False),
        (None, [], None, False),  # nothing has persisted shell.json yet
    ],
)
def test_the_anchor_follows_our_clock_onto_the_bar_and_never_off_the_users(
    box: Box, anchor: str | None, layout: list, expected: str | None, blocked: bool
) -> None:
    path = shell(box, anchor=anchor or STOCK, layout=layout)
    if anchor is None:
        path.unlink()
    weather = (box.home / LINK).parent / "someone.weather"
    weather.mkdir(parents=True)
    (weather / "manifest.json").write_text('{"id": "someone.weather"}\n')
    (box.home / MARKER).parent.mkdir(parents=True)
    (box.home / MARKER).touch()  # the anchor is repaired on any run, marker or not
    tmp = Path(f"{path}.tmp")
    if blocked:
        tmp.mkdir()  # nothing can be written there
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert (anchor_of(path) if path.exists() else None) == expected
    assert "omarchy-plugin-enable" not in box.commands
    assert ("could not set bar.centerAnchor" in result.stderr) == blocked
    assert not tmp.exists() or not any(tmp.iterdir())  # no stale temp file left


def test_the_anchor_edit_waits_for_the_shells_own_write_to_land(box: Box) -> None:
    """Without the wait the edit reads the pre-set copy and the shell's pending write takes it back."""
    path = shell(box)
    box.stub("omarchy-bar", BAR_SET_LATE)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert bar(path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(path) == ID


@pytest.mark.parametrize("answering", [True, False])
def test_undo_restores_the_stock_format_the_anchor_and_the_plugins_directory(
    box: Box, answering: bool
) -> None:
    path = shell(box)
    box.run(INSTALL)
    if not answering:
        box.stub("omarchy-plugin-disable", "exit 1\n")  # no shell to hand the entry back
    box.reset()
    result = box.undo("bar-clock")
    assert result.returncode == 0, result.stderr
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", ID]]
    assert anchor_of(path) == STOCK
    assert not (box.home / LINK).exists()
    assert not (box.home / MARKER).exists()
    assert "omarchy-shell" in box.commands
    if answering:
        assert box.calls_of("omarchy-bar") == [
            ["omarchy-bar", "set", STOCK, "format", STOCK_FORMAT]
        ]
        assert bar(path) == [{"id": STOCK, "format": STOCK_FORMAT}]
    else:
        assert "omarchy-bar" not in box.commands


def test_the_manifest_claims_the_stock_clock_slot() -> None:
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID
    assert manifest["omarchy"] == {"clonedFrom": STOCK}
    assert manifest["entryPoints"] == {"barWidget": "BarWidget.qml"}
    # Only what the shell does not already default (shell.qml:1400-1405); no
    # defaultSection either — the clonedFrom swap inherits the stock slot.
    assert manifest["barWidget"] == {"category": "Time"}


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason="needs the installed Omarchy")
def test_the_widget_tracks_omarchys_stock_clock() -> None:
    """BarWidget.qml is the stock file plus this plugin's header and exactly the
    three deltas that header names — red on an Omarchy release that changes the
    clock, which is the signal to refresh the copy."""
    ours = (PLUGIN / "BarWidget.qml").read_text().splitlines()
    body = ours[next(n for n, ln in enumerate(ours) if ln.startswith("import ")) :]
    stock = (STOCK_CLOCK / "BarWidget.qml").read_text().splitlines()
    diff = difflib.unified_diff(stock, body, n=0, lineterm="")
    changed = [ln for ln in diff if ln[:1] in "+-" and not ln.startswith(("---", "+++"))]
    assert changed == [
        '+    if ("moduleName" in target) target.moduleName = root.moduleName',
        "+  onModuleNameChanged: injectPanel()",
        "-    precision: SystemClock.Minutes",
        "+    precision: SystemClock.Seconds",
        '-    source: Qt.resolvedUrl("Panel.qml")',
        '+    source: "file://" + Quickshell.env("OMARCHY_PATH")'
        ' + "/shell/plugins/panels/clock/Panel.qml"',
    ]


def declarations(source: str) -> dict[str, str]:
    """Every top-level `var`/`function`, name -> its text: to the comment block
    introducing the next one, which belongs to that one."""
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


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason="needs the installed Omarchy")
def test_model_js_is_omarchys_label_math_and_only_that() -> None:
    """Model.js is the subset of Omarchy's that BarWidget.qml calls, verbatim:
    the panel is loaded from Omarchy's tree by absolute URL and resolves
    `import "Model.js"` against its own directory, so the calendar half — the
    monthGrid the widget never calls — stays there (verified live, Qt 6.11)."""
    kept = """MS_PER_DAY CLOCK_FORMATS VERTICAL_CLOCK_FORMATS clockFormats clockFormatRing
        nextClockFormat isoWeekLiteral pad2 isoWeek""".split()
    ours = declarations((PLUGIN / "Model.js").read_text())
    stock = declarations((STOCK_CLOCK / "Model.js").read_text())
    assert sorted(ours) == sorted(kept)
    for name in kept:
        assert ours[name] == stock[name], f"{name} has drifted from Omarchy's"
    widget = (PLUGIN / "BarWidget.qml").read_text()
    assert set(re.findall(r"\bModel\.([A-Za-z0-9_]+)\(", widget)) <= set(kept)
    assert "monthGrid" not in ours and "monthGrid" in stock


@pytest.mark.skipif(not VALIDATE.exists(), reason="needs the installed Omarchy")
def test_the_installed_link_passes_omarchy_plugin_validate(box: Box) -> None:
    """The real validator, on the path the module installs — with the trailing
    slash it needs: without one its own `find … -type l` prints the link
    (bin/omarchy-plugin-validate:115) and it refuses the folder."""
    shell(box)
    box.run(INSTALL)
    ok, bare = (
        subprocess.run(["bash", str(VALIDATE), p], capture_output=True, text=True)
        for p in (f"{box.home / LINK}/", str(box.home / LINK))
    )
    assert ok.returncode == 0, ok.stderr
    assert bare.returncode == 1 and "symlink" in bare.stderr
