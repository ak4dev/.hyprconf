"""bin/hyprconf-monitor-preset: the chosen preset is copied into Omarchy's
Hyprland toggles directory (default/hypr/toggles.lua:4,11 require_all()s it
after monitors.lua), the layout reloaded and today's workspaces re-homed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MODULE = Path(__file__).parent
SCRIPT = MODULE / "bin" / "hyprconf-monitor-preset"
INSTALL = MODULE / "install"
TOGGLE = Path(".local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua")
PRESET = 'hl.monitor({ output = "HDMI-A-1", mode = "preferred" })\n'
# Faithful to bin/omarchy-hyprland-toggle:17,30-32,54, because `stock` hands
# its whole job over: off() is `rm -f $HOME/.local/state/omarchy/toggles/hypr/
# $1.lua`, and `hyprctl reload` follows every action.
TOGGLE_OFF = (
    '[[ ${2:-toggle} == off ]] || { echo "fake: only off" >&2; exit 1; }\n'
    'rm -f "$HOME/.local/state/omarchy/toggles/hypr/$1.lua"\n'
    "hyprctl reload >/dev/null\n"
)
# hyprctl answering `workspacerules -j` from a file the test writes.
HYPRCTL_RULES = 'if [[ ${1:-} == workspacerules ]]; then cat "$HOME/rules.json" 2>/dev/null; fi\n'


def _cfg(box, **files: str) -> Path:
    """Presets where the tool reads them: the box's own ~/.config/hypr."""
    cfg = box.home / ".config" / "hypr"
    cfg.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (cfg / name).write_text(body)
    return cfg


def _run(box, *args: str):
    box.stub("omarchy-hyprland-toggle", TOGGLE_OFF)
    return box.run(SCRIPT, *args)


def test_a_preset_is_copied_to_the_toggle_and_monitors_lua_is_untouched(box) -> None:
    """A copy, never a link; an edit to the preset is what the next switch applies."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET, "monitors.lua": "-- omarchy auto\n"})
    res = _run(box, "bedroom")
    assert res.returncode == 0, res.stderr
    toggle = box.home / TOGGLE
    assert toggle.is_file() and not toggle.is_symlink() and toggle.read_text() == PRESET
    monitors = box.home / ".config" / "hypr" / "monitors.lua"
    assert not monitors.is_symlink() and monitors.read_text() == "-- omarchy auto\n"
    assert ["hyprctl", "reload"] in box.calls_of("hyprctl")
    assert any("bedroom" in " ".join(c) for c in box.calls_of("omarchy-osd"))

    edited = PRESET + "-- edited on this desk\n"
    (box.home / ".config" / "hypr" / "pcMonitors.bedroom.lua").write_text(edited)
    assert _run(box, "bedroom").returncode == 0
    assert toggle.read_text() == edited


def test_every_seeded_preset_is_reachable_by_its_short_name(box) -> None:
    """Labels come from the seeded files: pcMonitors.<label>.lua and <label>Monitors.lua both resolve."""
    assert box.run(INSTALL).returncode == 0
    shipped = {
        p.name.removeprefix("pcMonitors.").removesuffix("Monitors.lua").removesuffix(".lua"): p
        for p in sorted(MODULE.glob("*Monitors*.lua"))
    }
    assert shipped, "the module ships no monitor presets"
    for label, preset in shipped.items():
        assert _run(box, label).returncode == 0, label
        assert (box.home / TOGGLE).read_bytes() == preset.read_bytes(), label
    assert _run(box, "stock").returncode == 0
    assert not (box.home / TOGGLE).exists()


@pytest.mark.parametrize("flag,code", [("-h", 0), ("", 1)], ids=["help", "no-argument"])
def test_usage_lists_the_presets_that_are_there(box, flag: str, code: int) -> None:
    """Derived from ~/.config/hypr, so a new preset needs no edit to the tool; -h exits 0."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET, "laptopMonitors.lua": PRESET})
    res = _run(box, *([flag] if flag else []))
    assert res.returncode == code, res.stderr
    listed = re.search(r"Presets: (.*)", res.stderr)
    assert listed and set(listed.group(1).split()) == {"bedroom", "laptop", "stock"}, res.stderr
    assert not box.calls_of("omarchy-notification-send")


@pytest.mark.parametrize("name", ["nonexistent", "../evil"], ids=["unknown", "traversal"])
def test_an_unknown_preset_exits_nonzero_notifies_and_writes_no_toggle(box, name: str) -> None:
    """No terminal on the hotkey path, so the failure is a notification; a label is never pasted into a path."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET})
    # ~/.config/evilMonitors.lua is where "$CONFIG_DIR/${1}Monitors.lua" with ../evil would land.
    (box.home / ".config" / "evilMonitors.lua").write_text('hl.monitor({ output = "" })\n')
    res = _run(box, name)
    assert res.returncode != 0
    assert f"Preset not found: {name}" in res.stderr
    assert any(name in " ".join(c) for c in box.calls_of("omarchy-notification-send"))
    assert not box.calls_of("hyprctl")
    assert not (box.home / TOGGLE).exists()


def test_existing_workspaces_are_rehomed_and_one_dpms_wake_follows(box) -> None:
    """A reload places only FUTURE workspaces; the wake is for an output that came back dark (bin/omarchy-hyprland-monitor-internal:12-14,22)."""
    _cfg(box, **{"pcMonitors.kitchen.lua": PRESET})
    (box.home / "rules.json").write_text(
        '[{"workspaceString":"1","monitor":"desc:Samsung Electric Company Odyssey G8"},'
        '{"workspaceString":"4","monitor":"desc:Acer Technologies CB282K"},'
        '{"workspaceString":"7","monitor":""},'
        '{"workspaceString":"special:magic","monitor":"desc:Acer Technologies CB282K"}]'
    )
    box.stub("hyprctl", HYPRCTL_RULES)
    assert _run(box, "kitchen").returncode == 0
    dispatched = [c[2] for c in box.calls_of("hyprctl") if len(c) > 2 and c[1] == "dispatch"]
    assert dispatched == [
        'hl.dsp.workspace.move({ workspace = 1, monitor = "desc:Samsung Electric Company'
        ' Odyssey G8" })',
        'hl.dsp.workspace.move({ workspace = 4, monitor = "desc:Acer Technologies CB282K" })',
        'hl.dsp.dpms({ action = "enable" })',
    ], dispatched


def test_stock_hands_over_to_omarchys_own_toggle(box) -> None:
    """`stock` IS this toggle's off (rule 1), and a second one with nothing to remove still delegates."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET, "monitors.lua": "-- omarchy auto\n"})
    assert _run(box, "bedroom").returncode == 0
    assert (box.home / TOGGLE).exists()
    box.reset()

    res = _run(box, "stock")
    assert res.returncode == 0, res.stderr
    assert not (box.home / TOGGLE).exists()
    assert (box.home / ".config" / "hypr" / "monitors.lua").read_text() == "-- omarchy auto\n"
    assert box.calls_of("omarchy-hyprland-toggle") == [
        ["omarchy-hyprland-toggle", "hyprconf-monitor-preset", "off"]
    ]
    assert box.calls_of("hyprctl") == [["hyprctl", "reload"]]  # the toggle's own
    assert any("stock" in " ".join(c) for c in box.calls_of("omarchy-osd"))

    box.reset()
    assert _run(box, "stock").returncode == 0
    assert len(box.calls_of("omarchy-hyprland-toggle")) == 1
