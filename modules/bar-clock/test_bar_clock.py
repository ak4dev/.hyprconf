"""modules/bar-clock: the format and the centre anchor it sets ONCE, the undo that puts
both back, and the parity of the copied widget with Omarchy's own. The link, the one
enable and the rest of the undo are the shared mechanism's, pinned per plugin folder in
tests/test_plugins_contract.py."""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

import pytest

from conftest import BAR_SET, NEEDS_OMARCHY, OMARCHY, Box, bar_shell

INSTALL = Path(__file__).parent / "install"
PLUGIN = Path(__file__).parent / "plugin"
ID = "hyprconf.clock"
STOCK = "omarchy.clock"
FORMAT = "hh:mm:ss AP"
STOCK_FORMAT = "dddd HH:mm"
LINK = f".config/omarchy/plugins/{ID}"
MARKER = ".local/state/hyprconf/clock-applied"
# The installed Omarchy, for the pins that need the real thing — not box.omarchy,
# which is a fixture cut to what the module reads.
STOCK_CLOCK = OMARCHY / "shell/plugins/panels/clock"

# The same write, persisted on a LATER event-loop turn as the shell's is
# (shell.qml:109-113 persistShellConfig, then a FileView setText): an anchor
# edit that does not wait for it is taken straight back 0.2 s later.
BAR_SET_LATE = BAR_SET.replace('&& mv "$json.t"', '&& { ( sleep 0.2; mv "$json.t"')[:-1] + ") & }\n"


def bar(path: Path) -> list[dict]:
    """The centre section's entries, as objects."""
    center = json.loads(path.read_text())["bar"]["layout"]["center"]
    return [e if isinstance(e, dict) else {"id": e} for e in center]


def anchor_of(path: Path) -> str:
    return json.loads(path.read_text())["bar"]["centerAnchor"]


def test_install_enables_it_once_with_the_format_and_the_anchor(box: Box) -> None:
    path = bar_shell(box)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert (box.home / MARKER).exists()
    assert box.calls_of("omarchy-bar") == [["omarchy-bar", "set", ID, "format", FORMAT]]
    assert bar(path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(path) == ID


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
    path = bar_shell(box, anchor=anchor or STOCK, layout=layout)
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
    path = bar_shell(box)
    box.stub("omarchy-bar", BAR_SET_LATE)
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert bar(path) == [{"id": ID, "format": FORMAT}]
    assert anchor_of(path) == ID


@pytest.mark.parametrize("answering", [True, False])
def test_undo_restores_the_stock_format_and_the_anchor(box: Box, answering: bool) -> None:
    path = bar_shell(box)
    box.run(INSTALL)
    if not answering:
        box.stub("omarchy-plugin-disable", "exit 1\n")  # no shell to hand the entry back
    box.reset()
    result = box.undo("bar-clock")
    assert result.returncode == 0, result.stderr
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", ID]]
    assert bar(path) == [{"id": STOCK, "format": STOCK_FORMAT}]
    assert anchor_of(path) == STOCK
    assert not (box.home / LINK).exists() and not (box.home / MARKER).exists()
    expected = [["omarchy-bar", "set", STOCK, "format", STOCK_FORMAT]] if answering else []
    assert box.calls_of("omarchy-bar") == expected


def test_undo_leaves_a_stock_clock_the_user_went_back_to_alone(box: Box) -> None:
    """`omarchy plugin disable` sticks (README › Settings), and a disable answers "ok" for
    an id on no section (shell.qml:1620-1621): the format they then set on the stock clock
    is theirs, not a format of ours to reset."""
    path = bar_shell(box)
    box.run(INSTALL)
    theirs = [{"id": STOCK, "format": "HH:mm"}]
    bar_shell(box, anchor=STOCK, layout=theirs)
    box.reset()
    assert box.undo("bar-clock").returncode == 0
    assert bar(path) == theirs and anchor_of(path) == STOCK
    assert not {"omarchy-plugin-disable", "omarchy-bar"} & set(box.commands)
    assert not (box.home / LINK).exists() and not (box.home / MARKER).exists()


def test_the_manifest_claims_the_stock_clock_slot() -> None:
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    assert manifest["id"] == ID
    assert manifest["omarchy"] == {"clonedFrom": STOCK}
    assert manifest["entryPoints"] == {"barWidget": "BarWidget.qml"}
    # Only what the shell does not already default (shell.qml:1400-1405); no
    # defaultSection either — the clonedFrom swap inherits the stock slot.
    assert manifest["barWidget"] == {"category": "Time"}


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason=NEEDS_OMARCHY)
def test_the_widget_tracks_omarchys_stock_clock() -> None:
    """BarWidget.qml is the stock file plus this plugin's header and exactly the
    two deltas that header names — red on an Omarchy release that changes the
    clock, which is the signal to refresh the copy. The stock default `format`
    is pinned here too: it is what install's `undo` puts back."""
    ours = (PLUGIN / "BarWidget.qml").read_text().splitlines()
    body = ours[next(n for n, ln in enumerate(ours) if ln.startswith("import ")) :]
    stock = (STOCK_CLOCK / "BarWidget.qml").read_text()
    diff = difflib.unified_diff(stock.splitlines(), body, n=0, lineterm="")
    changed = [ln for ln in diff if ln[:1] in "+-" and not ln.startswith(("---", "+++"))]
    assert changed == [
        "-    precision: SystemClock.Minutes",
        "+    precision: SystemClock.Seconds",
        '-    source: Qt.resolvedUrl("Panel.qml")',
        '+    source: "file://" + Quickshell.env("OMARCHY_PATH")'
        ' + "/shell/plugins/panels/clock/Panel.qml"',
    ]
    assert f'setting("format", "{STOCK_FORMAT}")' in stock


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


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason=NEEDS_OMARCHY)
def test_model_js_is_omarchys_label_math_and_only_that() -> None:
    """Model.js is the subset of Omarchy's that BarWidget.qml calls, verbatim; the
    calendar half — the monthGrid the widget never calls — stays in Omarchy's tree
    (BarWidget.qml's header, delta 2; verified live, Qt 6.11)."""
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
