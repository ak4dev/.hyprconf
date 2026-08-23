"""Tests for hyprconf.keybinds — keybind parser and writer (Lua ``hl.bind`` form)."""

from __future__ import annotations

from pathlib import Path

from hyprconf.keybinds import (
    add_keybind,
    read_keybinds_with_location,
    update_keybind,
)

KEYBINDS_LUA = """\
local mainMod = "SUPER"
hl.bind(mainMod .. " + T", hl.dsp.exec_cmd("kitty"))
hl.bind(mainMod .. " + SHIFT + Q", hl.dsp.window.close())
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl set 5%+"), { locked = true, repeating = true })
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kb_file(hypr_dir: Path, content: str = KEYBINDS_LUA) -> Path:
    p = hypr_dir / "keybinds.lua"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_keybinds_with_location
# ---------------------------------------------------------------------------


def test_reads_basic_bind(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.lua")
    kinds = {e.kind for e in entries}
    assert "bind" in kinds


def test_reads_all_bind_kinds(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.lua")
    kinds = {e.kind for e in entries}
    # {locked=true} -> "bindl"; {locked=true, repeating=true} -> "bindle"
    # (canonical flag order, not the hyprlang-era "bindel" spelling — these
    # are reconstructed display labels, not round-tripped literal text)
    assert kinds == {"bind", "bindl", "bindle", "bindm"}


def test_variable_expansion(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.lua")
    # local mainMod = "SUPER" should be resolved in the concatenated key expr
    mod_entries = [e for e in entries if "SUPER" in e.mods]
    assert len(mod_entries) >= 3


def test_entry_fields(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.lua")
    kitty_entry = next(e for e in entries if e.dispatcher == "exec_cmd" and "kitty" in e.args)
    assert kitty_entry.key == "T"
    assert kitty_entry.mods == "SUPER"
    assert kitty_entry.kind == "bind"


def test_raw_line_preserved(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.lua")
    for e in entries:
        assert "mainMod" in e.raw_line or e.kind in ("bindl", "bindle", "bindm")


def test_line_idx_correct(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    p = hypr_dir / "keybinds.lua"
    entries = read_keybinds_with_location(p)
    for entry in entries:
        assert entry.file_path == p
        assert entry.line_idx >= 0
        lines = p.read_text().splitlines()
        assert entry.line_idx < len(lines)


def test_empty_file(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text("")
    assert read_keybinds_with_location(p) == []


def test_missing_file(hypr_dir: Path) -> None:
    p = hypr_dir / "nonexistent.lua"
    assert read_keybinds_with_location(p) == []


def test_ignores_comments(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text(
        '-- hl.bind("SUPER + X", hl.dsp.exec_cmd("foo"))\nhl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n'
    )
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    assert entries[0].args == "kitty"


# ---------------------------------------------------------------------------
# add_keybind
# ---------------------------------------------------------------------------


def test_add_keybind_appends(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text("")
    assert add_keybind("bind", "SUPER", "F", "exec", "firefox", file=p) is True
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    assert entries[0].key == "F"
    assert entries[0].args == "firefox"


def test_add_keybind_preserves_existing(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    add_keybind("bind", "SUPER", "F", "exec", "firefox", file=p)
    entries = read_keybinds_with_location(p)
    assert len(entries) == 2


def test_add_keybind_formats_correctly(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text("")
    add_keybind("bindl", "", "XF86AudioPlay", "exec", "playerctl play-pause", file=p)
    text = p.read_text()
    assert (
        'hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })'
        in text
    )


# ---------------------------------------------------------------------------
# update_keybind
# ---------------------------------------------------------------------------


def test_update_keybind_changes_args(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    entries = read_keybinds_with_location(p)
    e = entries[0]
    assert (
        update_keybind(e.file_path, e.line_idx, "bind", "SUPER", "T", "exec", "alacritty") is True
    )
    updated = read_keybinds_with_location(p)
    assert updated[0].args == "alacritty"


def test_update_keybind_changes_kind(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    entries = read_keybinds_with_location(p)
    e = entries[0]
    update_keybind(e.file_path, e.line_idx, "binde", "SUPER", "T", "exec", "kitty")
    updated = read_keybinds_with_location(p)
    assert updated[0].kind == "binde"


def test_update_keybind_invalid_idx(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    assert update_keybind(p, 999, "bind", "SUPER", "T", "exec", "kitty") is False


# ---------------------------------------------------------------------------
# Default path (covers KEYBINDS_FILE default in read_keybinds_with_location)
# ---------------------------------------------------------------------------


def test_read_keybinds_with_location_uses_default_path(hypr_dir: Path) -> None:
    """Calling without a file arg should use KEYBINDS_FILE."""
    from hyprconf.keybinds import KEYBINDS_FILE, read_keybinds_with_location

    KEYBINDS_FILE.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    entries = read_keybinds_with_location()  # no file arg → uses KEYBINDS_FILE
    assert len(entries) == 1
    assert entries[0].dispatcher == "exec_cmd"


# ---------------------------------------------------------------------------
# add_keybind default path
# ---------------------------------------------------------------------------


def test_add_keybind_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.keybinds import KEYBINDS_FILE, add_keybind, read_keybinds_with_location

    KEYBINDS_FILE.write_text("")
    add_keybind("bind", "SUPER", "F", "exec", "firefox")  # no file arg
    entries = read_keybinds_with_location(KEYBINDS_FILE)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# require()/try_require() following — the Lua analogue of hyprlang's
# `source = …` (plain and glob) directive-following
# ---------------------------------------------------------------------------


def test_read_follows_require_include(hypr_dir: Path) -> None:
    sub = hypr_dir / "extra_keybinds.lua"
    sub.write_text('hl.bind("SUPER + E", hl.dsp.exec_cmd("nemo"))\n')
    main_kb = hypr_dir / "keybinds.lua"
    main_kb.write_text(
        'require("extra_keybinds")\nhl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n'
    )
    entries = read_keybinds_with_location(main_kb, follow_sources=True)
    dispatchers = {e.dispatcher for e in entries}
    assert "exec_cmd" in dispatchers
    assert len(entries) == 2


def test_read_follows_try_require_include(hypr_dir: Path) -> None:
    """try_require(...) (used for optional conf.d modules) is followed the same way.

    conf.d modules are required by their bare name (e.g. "extra", not
    "conf.d.extra") — see the resolve_require_paths docstring for why: Lua's
    `require` converts every "." to a path separator, so a dotted name can't
    address conf.d itself (a directory literally named with a dot).
    """
    (hypr_dir / "conf.d").mkdir(exist_ok=True)
    sub = hypr_dir / "conf.d" / "extra.lua"
    sub.write_text('hl.bind("SUPER + A", hl.dsp.exec_cmd("app1"))\n')
    main_kb = hypr_dir / "keybinds.lua"
    main_kb.write_text('try_require("extra")\n')
    entries = read_keybinds_with_location(main_kb, follow_sources=True)
    assert any(e.args == "app1" for e in entries)


# ---------------------------------------------------------------------------
# Edge cases: malformed input
# ---------------------------------------------------------------------------


def test_read_keybinds_malformed_lines(hypr_dir: Path) -> None:
    """Lines that aren't a complete, well-formed hl.bind(...) call are skipped."""
    conf = hypr_dir / "keybinds.lua"
    conf.write_text(
        'local mainMod = "SUPER"\n'
        'hl.bind(mainMod .. " + T", hl.dsp.exec_cmd("kitty"))\n'
        "this is not a keybind line\n"
        "hl.bind()\n"
        'hl.bind(mainMod .. " + SHIFT + Q"\n'  # missing closing paren
        'hl.bind(mainMod .. " + R", hl.dsp.exec_cmd("rofi"))\n'
    )
    entries = read_keybinds_with_location(conf)
    assert len(entries) == 2
    assert entries[0].key == "T"
    assert entries[1].key == "R"


def test_read_keybinds_blank_and_comment_lines(hypr_dir: Path) -> None:
    """Blank lines and comments are ignored."""
    conf = hypr_dir / "keybinds.lua"
    conf.write_text(
        '\n\n-- This is a comment\nhl.bind("SUPER + X", hl.dsp.exec_cmd("xterm"))\n   \n-- Another comment\n'
    )
    entries = read_keybinds_with_location(conf)
    assert len(entries) == 1
    assert entries[0].key == "X"


# ---------------------------------------------------------------------------
# The shipped keybinds themselves — flags whose absence is invisible until the
# moment it hurts (a black panel, a smeared screenshot).
# ---------------------------------------------------------------------------

SHIPPED_KEYBINDS = Path(__file__).resolve().parents[2] / "stow/hypr/.config/hypr/keybinds.lua"


def _shipped() -> str:
    return SHIPPED_KEYBINDS.read_text(encoding="utf-8")


def test_brightness_keys_go_through_the_wrapper() -> None:
    """A bare `brightnessctl set` walks the panel to 0, dims a keyboard LED on
    machines with no backlight, and reports nothing. hyprconf-brightness owns
    all three (see tests/unit/test_brightness.py); the binds must route to it."""
    binds = [ln for ln in _shipped().splitlines() if "XF86MonBrightness" in ln]
    assert binds, "no brightness keybinds are shipped"
    for line in binds:
        assert "hyprconf-brightness" in line, (
            f"brightness bind bypasses the wrapper: {line.strip()}"
        )
        assert "brightnessctl" not in line, (
            f"brightness bind calls brightnessctl directly: {line.strip()}"
        )


def test_region_screenshot_freezes_the_screen() -> None:
    """Without it the capture is whatever redrew while the region was dragged,
    not what was on screen when the key was pressed."""
    shots = [ln for ln in _shipped().splitlines() if "hyprshot" in ln]
    assert shots, "no screenshot keybind is shipped"
    for line in shots:
        assert "--freeze" in line or " -z" in line, f"screenshot does not freeze: {line.strip()}"
