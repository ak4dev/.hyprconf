"""bin/hyprconf-monitor-preset — the whole tool, in one file.

Verifies:
- applying a preset COPIES it to Omarchy's Hyprland toggles directory
  (~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua — what
  default/hypr/toggles.lua:4,11 require_all()s after ~/.config/hypr/monitors.lua,
  so its hl.monitor calls win) and reloads; monitors.lua is never touched
- every preset the module seeds is reachable by its short name, and the usage
  line is derived from the same files rather than restating them
- the existing workspaces are re-homed from Hyprland's own parsed rules, and a
  single dpms wake follows the switch
- `stock` hands the removal to omarchy-hyprland-toggle, idempotently
- a bad or missing argument exits non-zero, says so through Omarchy's
  notification (the tool runs from a hotkey, where stderr goes nowhere a human
  can see) and writes no toggle

The box's fakes stand in for hyprctl and the omarchy-* commands: the real ones
would reload the developer's compositor and move their workspaces.
"""

from __future__ import annotations

import re
from pathlib import Path

MODULE = Path(__file__).parent
SCRIPT = MODULE / "bin" / "hyprconf-monitor-preset"
INSTALL = MODULE / "install"
TOGGLE = Path(".local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua")

PRESET = 'hl.monitor({ output = "HDMI-A-1", mode = "preferred" })\n'

# Faithful to bin/omarchy-hyprland-toggle:17,30-32,54 (Omarchy 4.0.3-1),
# because `stock` hands its whole job over: off() is `rm -f "$FLAG_FILE"` with
# FLAG_FILE=$HOME/.local/state/omarchy/toggles/hypr/$1.lua, and `hyprctl
# reload` runs after every action. A record-only stub would leave the toggle
# file in place and the end-state assertions meaningless.
TOGGLE_OFF = (
    '[[ ${2:-toggle} == off ]] || { echo "fake: only off" >&2; exit 1; }\n'
    'rm -f "$HOME/.local/state/omarchy/toggles/hypr/$1.lua"\n'
    "hyprctl reload >/dev/null\n"
)
# hyprctl answering `workspacerules -j` from a file the test writes.
HYPRCTL_RULES = 'if [[ ${1:-} == workspacerules ]]; then cat "$HOME/rules.json" 2>/dev/null; fi\n'


def _cfg(box, **files: str) -> Path:
    """Presets where the tool reads them — the box's ~/.config/hypr, which is
    also where an edit between two runs lands."""
    cfg = box.home / ".config" / "hypr"
    cfg.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (cfg / name).write_text(body)
    return cfg


def _run(box, *args: str):
    box.stub("omarchy-hyprland-toggle", TOGGLE_OFF)
    return box.run(SCRIPT, *args)


def _shipped() -> dict[str, Path]:
    """Every preset the module ships, by the short name the tool takes — the
    two shapes, pcMonitors.<label>.lua and <label>Monitors.lua, derived the
    same way the tool derives them."""
    out = {}
    for preset in sorted(MODULE.glob("*Monitors*.lua")):
        label = preset.name.removeprefix("pcMonitors.").removesuffix("Monitors.lua")
        out[label.removesuffix(".lua")] = preset
    return out


def test_every_external_the_tool_calls_has_a_fake(box) -> None:
    """If the tool grows a new omarchy-*/hyprctl call, this fails before that
    call can reach the developer's real desktop from a test."""
    code = "\n".join(
        ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")
    )
    called = set(re.findall(r"\b(hyprctl|omarchy-[a-z-]+)\b", code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= box.fakes, f"unstubbed externals: {called - box.fakes}"


def test_a_preset_is_copied_to_the_toggle_and_monitors_lua_is_untouched(box) -> None:
    """The preset lands as a COPY in Omarchy's toggles directory — never a
    link, so nothing Omarchy does to that directory reaches it — and Omarchy's
    own monitors.lua is left exactly as it was: Omarchy keeps writing to it
    (omarchy-hyprland-monitor-scaling seds the scale lines in place)."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET, "monitors.lua": "-- omarchy auto\n"})

    res = _run(box, "bedroom")
    assert res.returncode == 0, res.stderr
    toggle = box.home / TOGGLE
    assert toggle.is_file() and not toggle.is_symlink()
    assert toggle.read_text() == PRESET
    monitors = box.home / ".config" / "hypr" / "monitors.lua"
    assert not monitors.is_symlink() and monitors.read_text() == "-- omarchy auto\n"
    assert ["hyprctl", "reload"] in box.calls_of("hyprctl")
    assert any("bedroom" in " ".join(c) for c in box.calls_of("omarchy-osd"))

    # An edit to a preset is what the next switch applies: the copy is
    # unconditional, and this is the only run that overwrites the toggle file.
    edited = PRESET + "-- edited on this desk\n"
    (box.home / ".config" / "hypr" / "pcMonitors.bedroom.lua").write_text(edited)
    assert _run(box, "bedroom").returncode == 0
    assert toggle.read_text() == edited


def test_every_seeded_preset_is_reachable_by_its_short_name(box) -> None:
    """The names come from the files the module seeds, not from a list: both
    shipped shapes — pcMonitors.<label>.lua and <label>Monitors.lua — resolve
    to one label, and `stock` takes the layout back."""
    assert box.run(INSTALL).returncode == 0
    shipped = _shipped()
    assert shipped, "the module ships no monitor presets"
    for label, preset in shipped.items():
        res = _run(box, label)
        assert res.returncode == 0, (label, res.stderr)
        assert (box.home / TOGGLE).read_bytes() == preset.read_bytes(), label
    assert _run(box, "stock").returncode == 0
    assert not (box.home / TOGGLE).exists()


def test_usage_lists_the_presets_that_are_there(box) -> None:
    """-h/--help exits 0 and names what can actually be applied — derived from
    ~/.config/hypr, so a new preset needs no edit to this tool. Without the
    branch they reached the "not found" critical desktop notification."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET, "laptopMonitors.lua": PRESET})
    for flag in ("-h", "--help"):
        box.reset()
        res = _run(box, flag)
        assert res.returncode == 0, (flag, res.stderr)
        assert "Usage:" in res.stderr
        assert re.search(r"Presets:.*\bbedroom\b", res.stderr), res.stderr
        assert re.search(r"Presets:.*\blaptop\b", res.stderr), res.stderr
        assert re.search(r"Presets:.*\bstock\b", res.stderr), res.stderr
        assert not box.calls_of("omarchy-notification-send"), flag


def test_no_argument_is_a_usage_error(box) -> None:
    _cfg(box)
    res = _run(box)
    assert res.returncode != 0
    assert "Usage" in res.stderr and "stock" in res.stderr


def test_an_unknown_preset_exits_nonzero_and_notifies(box) -> None:
    """The hotkey path has no terminal to read stderr from, so the failure is
    a desktop notification."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET})

    res = _run(box, "nonexistent")
    assert res.returncode != 0
    assert "Preset not found: nonexistent" in res.stderr
    assert any("nonexistent" in " ".join(c) for c in box.calls_of("omarchy-notification-send"))
    assert not box.calls_of("hyprctl")
    assert not (box.home / TOGGLE).exists()


def test_a_preset_name_can_never_name_a_file_outside_the_config_dir(box) -> None:
    """The argument is matched against labels derived from ~/.config/hypr's own
    listing and is never pasted into a path, so traversal has nothing to
    traverse — whatever it is spelled as."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET})
    (box.home / "evilMonitors.lua").write_text('hl.monitor({ output = "" })\n')

    res = _run(box, "../evil")
    assert res.returncode != 0
    assert not (box.home / TOGGLE).exists()


def test_existing_workspaces_are_rehomed_from_hyprlands_own_rules(box) -> None:
    """Workspace rules place only FUTURE workspaces: on a reload Hyprland
    leaves existing ones where they are, so the switch moves today's
    explicitly. The rules come back from `hyprctl workspacerules -j` after the
    reload — Omarchy declares none with a monitor, so each one is the preset's
    — and a rule without a monitor (the one omarchy-hyprland-workspace-layout-
    toggle writes) or with a non-numeric workspace is not a move."""
    _cfg(box, **{"pcMonitors.kitchen.lua": PRESET})
    (box.home / "rules.json").write_text(
        '[{"workspaceString":"1","monitor":"desc:Samsung Electric Company Odyssey G8"},'
        '{"workspaceString":"4","monitor":"desc:Acer Technologies CB282K"},'
        '{"workspaceString":"7","monitor":""},'
        '{"workspaceString":"special:magic","monitor":"desc:Acer Technologies CB282K"}]'
    )
    box.stub("hyprctl", HYPRCTL_RULES)

    assert _run(box, "kitchen").returncode == 0
    moves = [" ".join(c) for c in box.calls_of("hyprctl") if "workspace.move" in " ".join(c)]
    assert moves == [
        "hyprctl dispatch hl.dsp.workspace.move({ workspace = 1, monitor = "
        '"desc:Samsung Electric Company Odyssey G8" })',
        "hyprctl dispatch hl.dsp.workspace.move({ workspace = 4, monitor = "
        '"desc:Acer Technologies CB282K" })',
    ], moves


def test_a_dpms_wake_follows_every_switch(box) -> None:
    """An output flipping disabled→enabled through the reload can hit a
    failed-CRTC restore and stay dark; one unconditional wake is what Omarchy
    does after its own user-initiated enable
    (bin/omarchy-hyprland-monitor-internal:12-14,22)."""
    _cfg(box, **{"pcMonitors.bedroom.lua": PRESET})

    assert _run(box, "bedroom").returncode == 0
    wakes = [c for c in box.calls_of("hyprctl") if "dpms" in " ".join(c)]
    assert wakes == [["hyprctl", "dispatch", 'hl.dsp.dpms({ action = "enable" })']], wakes


def test_stock_hands_over_to_omarchys_own_toggle(box) -> None:
    """`stock` IS the toggle's off, so it runs Omarchy's own command rather
    than a copy of it (rule 1): the file goes, Hyprland reloads, and Omarchy's
    monitors.lua — untouched — is the only layout left. Idempotent: a second
    `stock` with nothing to remove still delegates, reloads and reports."""
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
    assert _run(box, "stock").returncode == 0  # again, with nothing to remove
    assert len(box.calls_of("omarchy-hyprland-toggle")) == 1
