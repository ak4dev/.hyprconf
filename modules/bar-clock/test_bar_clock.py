"""modules/bar-clock: Omarchy's own clock kept on a format that prints seconds — set on any
run that finds one printing none, left alone otherwise, put back to stock by the undo — and
the retirement of the hyprconf.clock plugin this module shipped before 10.0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import NEEDS_OMARCHY, OMARCHY, Box, bar_shell

INSTALL = Path(__file__).parent / "install"
CLOCK = "omarchy.clock"
FORMAT = "hh:mm:ss AP"
STOCK_FORMAT = "dddd HH:mm"
SET = ["omarchy-bar", "set", CLOCK, "format", FORMAT]
OLD = "hyprconf.clock"
OLD_LINK = f".config/omarchy/plugins/{OLD}"
OLD_MARKER = ".local/state/hyprconf/clock-applied"
# The installed Omarchy, for the pins that need the real thing — not box.omarchy,
# which is a fixture cut to what the module reads.
STOCK_CLOCK = OMARCHY / "shell/plugins/panels/clock"


def bar(path: Path) -> list[dict]:
    """The centre box's entries, as objects."""
    center = json.loads(path.read_text())["bar"]["layout"]["center"]
    return [e if isinstance(e, dict) else {"id": e} for e in center]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"id": CLOCK, "format": STOCK_FORMAT}, {"id": CLOCK, "format": FORMAT}),  # stock
        # where a right-click walk from ours can land: most of the ring prints no seconds
        ({"id": CLOCK, "format": "ddd d MMM h:mm AP"}, {"id": CLOCK, "format": FORMAT}),
        ({"id": CLOCK}, {"id": CLOCK, "format": FORMAT}),  # no format: the widget's default
        (CLOCK, {"id": CLOCK, "format": FORMAT}),  # a bare-id entry (bin/omarchy-bar:190)
        ({"id": CLOCK, "format": "h:mm 'secs'"}, {"id": CLOCK, "format": FORMAT}),  # a literal
        ({"id": CLOCK, "format": "h:mm 'as of"}, {"id": CLOCK, "format": FORMAT}),  # unclosed
        # still the user's: a format that prints seconds, a preset of Omarchy's ring included
        ({"id": CLOCK, "format": "HH:mm:ss"}, {"id": CLOCK, "format": "HH:mm:ss"}),
        ({"id": CLOCK, "format": "dddd h:mm:ss AP"}, {"id": CLOCK, "format": "dddd h:mm:ss AP"}),
        # and a bar that carries another clock, or none: nothing of ours to set
        ({"id": "testuser.clock", "format": "HH:mm"}, {"id": "testuser.clock", "format": "HH:mm"}),
    ],
)
def test_a_clock_printing_no_seconds_gets_ours_on_any_run(
    box: Box, entry: dict | str, expected: dict
) -> None:
    """The one setting re-asserted on every run (rule 5's exception), through Omarchy's own
    `omarchy bar set`; a second run writes nothing and calls nothing."""
    path = bar_shell(box, layout=[entry])
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert bar(path) == [expected]
    changed = expected != (entry if isinstance(entry, dict) else {"id": entry})
    assert box.calls_of("omarchy-bar") == ([SET] if changed else [])
    assert ("showed no seconds" in result.stdout) == changed
    before = box.snapshot()
    box.reset()
    assert box.run(INSTALL).returncode == 0
    assert box.snapshot() == before and box.commands == []


def test_a_box_with_no_shell_json_of_its_own_is_read_as_omarchys_default_bar(box: Box) -> None:
    """The shell shows the shipped bar until something persists a file
    (bin/omarchy-shell-config:20-26), and that bar's clock prints no seconds."""
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert box.calls_of("omarchy-bar") == [SET]
    assert box.files() == set(), "the install wrote a shell.json itself"


def test_no_shell_answering_says_so_and_leaves_the_file_alone(box: Box) -> None:
    """`omarchy bar set` is the running shell's write (bin/omarchy-bar:453-454): with none,
    the run still succeeds — it must not fail the module loop — and the next one retries."""
    path = bar_shell(box)
    before = path.read_bytes()
    box.stub("omarchy-bar", "exit 1\n")
    result = box.run(INSTALL)
    assert result.returncode == 0, result.stderr
    assert "retried on the next run" in result.stdout and "showed no seconds" not in result.stdout
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [(FORMAT, STOCK_FORMAT), ("HH:mm:ss", "HH:mm:ss"), (STOCK_FORMAT, STOCK_FORMAT)],
    ids=["ours", "the-users-own", "stock"],
)
def test_undo_puts_the_stock_format_back_only_over_ours(box: Box, fmt: str, expected: str) -> None:
    path = bar_shell(box, layout=[{"id": CLOCK, "format": fmt}])
    result = box.undo("bar-clock")
    assert result.returncode == 0, result.stderr
    assert bar(path) == [{"id": CLOCK, "format": expected}]
    assert len(box.calls_of("omarchy-bar")) == (fmt != expected)


def test_undo_on_a_box_that_never_installed_writes_and_calls_nothing(box: Box) -> None:
    assert box.undo("bar-clock").returncode == 0
    assert box.files() == set() and box.commands == []


@pytest.mark.parametrize("answering", [True, False])
@pytest.mark.parametrize("verb", ["", "undo"])
def test_the_plugin_an_earlier_release_linked_is_retired(
    box: Box, answering: bool, verb: str
) -> None:
    """Up to 9.x this module linked its own copy of the clock in as hyprconf.clock. The pull
    that brings 10.0 leaves that link dangling, so the first run hands the slot back to
    omarchy.clock — every setting of the entry kept — through the shell when it still knows
    the plugin, in shell.json itself when it does not, and drops the link and the marker."""
    entry = {"id": OLD, "format": FORMAT, "birthYear": 1987}
    path = bar_shell(box, layout=[entry])
    link, marker = box.home / OLD_LINK, box.home / OLD_MARKER
    link.parent.mkdir(parents=True)
    link.symlink_to(box.tmp / "checkout/modules/bar-clock/plugin")  # gone with the pull
    marker.parent.mkdir(parents=True)
    marker.touch()
    renamed = f"""json="$HOME/.config/omarchy/shell.json"
jq '.bar.layout.center |= map(if .id == "{OLD}" then .id = "{CLOCK}" else . end)' \\
    "$json" > "$json.t" && mv "$json.t" "$json"\n"""
    box.stub("omarchy-plugin-disable", renamed if answering else "exit 1\n")

    result = box.run(INSTALL, *([verb] if verb else []))
    assert result.returncode == 0, result.stderr
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", OLD]]
    assert not link.is_symlink() and not marker.exists()
    assert "hyprconf.clock retired" in result.stdout
    assert box.calls_of("omarchy-shell") == [["omarchy-shell", "shell", "rescanPlugins"]]
    kept = {"id": CLOCK, "birthYear": 1987}
    assert bar(path) == [kept | {"format": STOCK_FORMAT if verb else FORMAT}]

    box.reset()
    again = box.run(INSTALL)
    assert again.returncode == 0, again.stderr
    assert "omarchy-plugin-disable" not in box.commands and "retired" not in again.stdout


def test_a_real_folder_or_checkout_of_that_id_is_not_ours_to_retire(box: Box) -> None:
    """Only the link an earlier install made: a folder there is someone's own plugin."""
    path = bar_shell(box, layout=[{"id": OLD, "format": FORMAT}])
    folder = box.home / OLD_LINK
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}\n")
    assert box.run(INSTALL).returncode == 0
    assert (folder / "manifest.json").read_text() == "{}\n"
    assert bar(path) == [{"id": OLD, "format": FORMAT}] and box.commands == []


@pytest.mark.skipif(not STOCK_CLOCK.is_dir(), reason=NEEDS_OMARCHY)
def test_omarchys_clock_still_ticks_seconds_for_a_format_that_prints_them() -> None:
    """What lets this module ship no widget, and the three facts its install mirrors: the
    stock default format `undo` puts back, the seconds test, and the tick it switches —
    red on an Omarchy release that changes the clock."""
    widget = (STOCK_CLOCK / "BarWidget.qml").read_text()
    model = (STOCK_CLOCK / "Model.js").read_text()
    assert f'setting("format", "{STOCK_FORMAT}")' in widget
    assert "showsSeconds: Model.clockNeedsSeconds(activeFormat)" in widget
    assert "step: root.showsSeconds ? 1000 : 60000" in widget
    assert """return /s/.test(text.replace(/'[^']*'?/g, ""))""" in model
    shipped = json.loads((OMARCHY / "config/omarchy/shell.json").read_text())
    clocks = [e for e in shipped["bar"]["layout"]["center"] if e["id"] == CLOCK]
    assert [c["format"] for c in clocks] == [STOCK_FORMAT]
