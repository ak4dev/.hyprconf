"""Tests for hyprconf.keybinds — parser and writers for the three call forms
that appear in Omarchy's bindings.lua: ``hl.bind``, ``o.bind`` and the
overlay's own ``rebind``."""

from __future__ import annotations

import re
from pathlib import Path

from hyprconf.keybinds import (
    KeybindEntry,
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

# A slice of the overlay's bindings.lua: the local helpers (whose bodies must
# not be mistaken for binds), unbinds, and all three call forms.
BINDINGS_LUA = """\
local mainMod = "SUPER"

local function rebind(keys, description, dispatcher, options)
  hl.unbind(keys)
  o.bind(keys, description, dispatcher, options)
end

local function unbind_keycode(mods, key)
  local code = KEYCODE[key]
  if code then hl.unbind(mods .. " + code:" .. code) end
end

rebind(mainMod .. " + T", "Terminal", hl.dsp.exec_cmd("omarchy-launch-terminal"))
hl.unbind(mainMod .. " + SHIFT + Q")
o.bind(mainMod .. " + SHIFT + Q", "Log out", "omarchy-system-logout")
o.bind(mainMod .. " + RETURN", "Terminal", { omarchy = "terminal" })
unbind_keycode(mainMod, "1")
rebind(mainMod .. " + 1",          "Switch to workspace 1", hl.dsp.focus({ workspace = 1 }))
rebind(mainMod .. " + SHIFT + left",  "Shrink window left", hl.dsp.window.resize({ x = -40, y = 0 }),  { repeating = true })
rebind(mainMod .. " + mouse:272", "Move window", hl.dsp.window.drag(),   { mouse = true })
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true, description = "Play" })
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kb_file(hypr_dir: Path, content: str = KEYBINDS_LUA) -> Path:
    p = hypr_dir / "bindings.lua"
    p.write_text(content)
    return p


def _by_key(entries: list[KeybindEntry], mods: str, key: str) -> KeybindEntry:
    return next(e for e in entries if e.mods == mods and e.key == key)


# ---------------------------------------------------------------------------
# read_keybinds_with_location — hl.bind form
# ---------------------------------------------------------------------------


def test_reads_basic_bind(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "bindings.lua")
    kinds = {e.kind for e in entries}
    assert "bind" in kinds


def test_reads_all_bind_kinds(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "bindings.lua")
    kinds = {e.kind for e in entries}
    # {locked=true} -> "bindl"; {locked=true, repeating=true} -> "bindle"
    # (canonical flag order, not the hyprlang-era "bindel" spelling — these
    # are reconstructed display labels, not round-tripped literal text)
    assert kinds == {"bind", "bindl", "bindle", "bindm"}


def test_variable_expansion(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "bindings.lua")
    # local mainMod = "SUPER" should be resolved in the concatenated key expr
    mod_entries = [e for e in entries if "SUPER" in e.mods]
    assert len(mod_entries) >= 3


def test_entry_fields(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "bindings.lua")
    kitty_entry = next(e for e in entries if e.dispatcher == "exec_cmd" and "kitty" in e.args)
    assert kitty_entry.key == "T"
    assert kitty_entry.mods == "SUPER"
    assert kitty_entry.kind == "bind"
    assert kitty_entry.call == "hl.bind"
    assert kitty_entry.description == ""


def test_raw_line_preserved(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "bindings.lua")
    for e in entries:
        assert "mainMod" in e.raw_line or e.kind in ("bindl", "bindle", "bindm")


def test_line_idx_correct(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    p = hypr_dir / "bindings.lua"
    entries = read_keybinds_with_location(p)
    for entry in entries:
        assert entry.file_path == p
        assert entry.line_idx >= 0
        lines = p.read_text().splitlines()
        assert entry.line_idx < len(lines)


def test_empty_file(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text("")
    assert read_keybinds_with_location(p) == []


def test_missing_file(hypr_dir: Path) -> None:
    p = hypr_dir / "nonexistent.lua"
    assert read_keybinds_with_location(p) == []


def test_ignores_comments(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text(
        '-- hl.bind("SUPER + X", hl.dsp.exec_cmd("foo"))\nhl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n'
    )
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    assert entries[0].args == "kitty"


# ---------------------------------------------------------------------------
# read_keybinds_with_location — o.bind / rebind forms (Omarchy's bindings.lua)
# ---------------------------------------------------------------------------


def test_rebind_form_is_parsed(hypr_dir: Path) -> None:
    entries = read_keybinds_with_location(_kb_file(hypr_dir, BINDINGS_LUA))
    e = _by_key(entries, "SUPER", "T")
    assert e.call == "rebind"
    assert e.description == "Terminal"
    assert e.dispatcher == "exec_cmd"
    assert e.args == "omarchy-launch-terminal"
    assert e.kind == "bind"


def test_o_bind_string_dispatcher_is_an_exec(hypr_dir: Path) -> None:
    """helpers.lua wraps a string dispatcher in hl.dsp.exec_cmd — shown as such."""
    entries = read_keybinds_with_location(_kb_file(hypr_dir, BINDINGS_LUA))
    e = _by_key(entries, "SUPER SHIFT", "Q")
    assert e.call == "o.bind"
    assert e.description == "Log out"
    assert (e.dispatcher, e.args) == ("exec_cmd", "omarchy-system-logout")


def test_o_bind_launch_table_shown_as_table_text(hypr_dir: Path) -> None:
    """{ omarchy = "terminal" } is resolved by command_from at load time; the
    parser displays the table verbatim and never tries to run it."""
    entries = read_keybinds_with_location(_kb_file(hypr_dir, BINDINGS_LUA))
    e = _by_key(entries, "SUPER", "RETURN")
    assert e.dispatcher == '{ omarchy = "terminal" }'
    assert e.args == ""
    assert e.description == "Terminal"


def test_table_arguments_and_opts_are_parsed(hypr_dir: Path) -> None:
    entries = read_keybinds_with_location(_kb_file(hypr_dir, BINDINGS_LUA))
    ws = _by_key(entries, "SUPER", "1")
    assert (ws.dispatcher, ws.args) == ("focus", "{ workspace = 1 }")
    resize = _by_key(entries, "SUPER SHIFT", "left")
    assert resize.dispatcher == "window.resize"
    assert resize.args == "{ x = -40, y = 0 }"
    assert resize.kind == "binde"
    assert _by_key(entries, "SUPER", "mouse:272").kind == "bindm"


def test_hl_bind_description_comes_from_opts(hypr_dir: Path) -> None:
    """o.bind stores its description as opts.description before calling
    hl.bind, so a raw hl.bind carrying one is read the same way."""
    entries = read_keybinds_with_location(_kb_file(hypr_dir, BINDINGS_LUA))
    e = _by_key(entries, "", "XF86AudioPlay")
    assert e.call == "hl.bind"
    assert e.description == "Play"
    assert e.kind == "bindl"


def test_helper_bodies_unbinds_and_locals_are_skipped(hypr_dir: Path) -> None:
    p = _kb_file(hypr_dir, BINDINGS_LUA)
    entries = read_keybinds_with_location(p)
    assert len(entries) == 7
    assert not any(e.key == "keys" for e in entries), "helper body parsed as a bind"
    lines = p.read_text().splitlines()
    for e in entries:
        assert re.match(r"^(rebind|o\.bind|hl\.bind)\(", lines[e.line_idx]), lines[e.line_idx]


# ---------------------------------------------------------------------------
# add_keybind — new binds are o.bind(keys, "description", dispatcher[, opts])
# ---------------------------------------------------------------------------


def test_add_keybind_appends(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text("")
    assert add_keybind("bind", "SUPER", "F", "exec", "firefox", file=p) is True
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    assert entries[0].key == "F"
    assert entries[0].args == "firefox"
    assert entries[0].call == "o.bind"


def test_add_keybind_preserves_existing(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    add_keybind("bind", "SUPER", "F", "exec", "firefox", file=p)
    entries = read_keybinds_with_location(p)
    assert len(entries) == 2


def test_add_keybind_writes_o_bind_with_description(hypr_dir: Path) -> None:
    """The description is the whole point of o.bind: it is what Omarchy's
    SUPER+K keybindings menu lists. An exec is written as the bare command
    string, which helpers.lua turns into hl.dsp.exec_cmd."""
    p = hypr_dir / "bindings.lua"
    p.write_text("")
    add_keybind("bindl", "", "XF86AudioPlay", "exec", "playerctl play-pause", p, "Play/pause")
    assert (
        'o.bind("XF86AudioPlay", "Play/pause", "playerctl play-pause", { locked = true })'
        in p.read_text()
    )


def test_add_keybind_uses_mainmod_when_the_file_defines_it(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text('local mainMod = "SUPER"\n')
    add_keybind("bind", "SUPER SHIFT", "F", "fullscreen", "", p, "Full screen")
    assert 'o.bind(mainMod .. " + SHIFT + F", "Full screen", hl.dsp.window.fullscreen())' in (
        p.read_text()
    )
    e = read_keybinds_with_location(p)[0]
    assert (e.mods, e.key, e.description) == ("SUPER SHIFT", "F", "Full screen")


def test_add_keybind_spells_out_mainmod_when_undefined(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text("")
    add_keybind("bind", "$mainMod", "F", "exec", "firefox", p, "Browser")
    assert 'o.bind("SUPER + F", "Browser", "firefox")' in p.read_text()


# ---------------------------------------------------------------------------
# update_keybind — keeps the line's call form and description
# ---------------------------------------------------------------------------


def test_update_keybind_changes_args(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    entries = read_keybinds_with_location(p)
    e = entries[0]
    assert (
        update_keybind(e.file_path, e.line_idx, "bind", "SUPER", "T", "exec", "alacritty") is True
    )
    updated = read_keybinds_with_location(p)
    assert updated[0].args == "alacritty"
    assert p.read_text().startswith("hl.bind(")


def test_update_keybind_changes_kind(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    entries = read_keybinds_with_location(p)
    e = entries[0]
    update_keybind(e.file_path, e.line_idx, "binde", "SUPER", "T", "exec", "kitty")
    updated = read_keybinds_with_location(p)
    assert updated[0].kind == "binde"


def test_update_keybind_invalid_idx(hypr_dir: Path) -> None:
    p = hypr_dir / "bindings.lua"
    p.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    assert update_keybind(p, 999, "bind", "SUPER", "T", "exec", "kitty") is False


def test_update_keeps_rebind_call_and_description(hypr_dir: Path) -> None:
    p = _kb_file(hypr_dir, BINDINGS_LUA)
    e = _by_key(read_keybinds_with_location(p), "SUPER", "T")
    assert update_keybind(p, e.line_idx, "bind", "SUPER", "T", "exec", "kitty") is True
    line = p.read_text().splitlines()[e.line_idx]
    assert line == 'rebind(mainMod .. " + T", "Terminal", "kitty")'


def test_update_can_change_the_description(hypr_dir: Path) -> None:
    p = _kb_file(hypr_dir, BINDINGS_LUA)
    e = _by_key(read_keybinds_with_location(p), "SUPER SHIFT", "Q")
    update_keybind(p, e.line_idx, e.kind, e.mods, e.key, e.dispatcher, e.args, "Sign out")
    line = p.read_text().splitlines()[e.line_idx]
    assert line == 'o.bind(mainMod .. " + SHIFT + Q", "Sign out", "omarchy-system-logout")'


def test_update_round_trips_table_args_and_opts(hypr_dir: Path) -> None:
    """A rewritten line must still be the Lua the parser read — table
    arguments stay tables, flags stay in the opts table."""
    p = _kb_file(hypr_dir, BINDINGS_LUA)
    entries = read_keybinds_with_location(p)
    for e in entries:
        assert update_keybind(p, e.line_idx, e.kind, e.mods, e.key, e.dispatcher, e.args)
    lines = p.read_text().splitlines()
    ws = _by_key(entries, "SUPER", "1")
    assert lines[ws.line_idx] == (
        'rebind(mainMod .. " + 1", "Switch to workspace 1", hl.dsp.focus({ workspace = 1 }))'
    )
    rs = _by_key(entries, "SUPER SHIFT", "left")
    assert lines[rs.line_idx] == (
        'rebind(mainMod .. " + SHIFT + left", "Shrink window left", '
        "hl.dsp.window.resize({ x = -40, y = 0 }), { repeating = true })"
    )
    launch = _by_key(entries, "SUPER", "RETURN")
    assert lines[launch.line_idx] == (
        'o.bind(mainMod .. " + RETURN", "Terminal", { omarchy = "terminal" })'
    )
    play = _by_key(entries, "", "XF86AudioPlay")
    assert lines[play.line_idx] == (
        'hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), '
        '{ locked = true, description = "Play" })'
    )
    reread = read_keybinds_with_location(p)
    assert [(e.mods, e.key, e.dispatcher, e.args, e.description, e.kind) for e in reread] == [
        (e.mods, e.key, e.dispatcher, e.args, e.description, e.kind) for e in entries
    ]


# ---------------------------------------------------------------------------
# Default path (covers KEYBINDS_FILE default in read_keybinds_with_location)
# ---------------------------------------------------------------------------


def test_read_keybinds_with_location_uses_default_path(hypr_dir: Path) -> None:
    """Calling without a file arg should use KEYBINDS_FILE (bindings.lua)."""
    from hyprconf.keybinds import KEYBINDS_FILE, read_keybinds_with_location

    assert KEYBINDS_FILE.name == "bindings.lua"
    KEYBINDS_FILE.write_text('hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    entries = read_keybinds_with_location()  # no file arg → uses KEYBINDS_FILE
    assert len(entries) == 1
    assert entries[0].dispatcher == "exec_cmd"


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
    main_kb = hypr_dir / "bindings.lua"
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
    main_kb = hypr_dir / "bindings.lua"
    main_kb.write_text('try_require("extra")\n')
    entries = read_keybinds_with_location(main_kb, follow_sources=True)
    assert any(e.args == "app1" for e in entries)


# ---------------------------------------------------------------------------
# Edge cases: malformed input
# ---------------------------------------------------------------------------


def test_read_keybinds_malformed_lines(hypr_dir: Path) -> None:
    """Lines that aren't a complete, well-formed bind call are skipped."""
    conf = hypr_dir / "bindings.lua"
    conf.write_text(
        'local mainMod = "SUPER"\n'
        'hl.bind(mainMod .. " + T", hl.dsp.exec_cmd("kitty"))\n'
        "this is not a keybind line\n"
        "hl.bind()\n"
        'hl.bind(mainMod .. " + SHIFT + Q"\n'  # missing closing paren
        'o.bind(mainMod .. " + X", hl.dsp.exec_cmd("no-description"))\n'  # o.bind needs 3 args
        'hl.bind(mainMod .. " + R", hl.dsp.exec_cmd("rofi"))\n'
    )
    entries = read_keybinds_with_location(conf)
    assert len(entries) == 2
    assert entries[0].key == "T"
    assert entries[1].key == "R"


def test_read_keybinds_blank_and_comment_lines(hypr_dir: Path) -> None:
    """Blank lines and comments are ignored."""
    conf = hypr_dir / "bindings.lua"
    conf.write_text(
        '\n\n-- This is a comment\nhl.bind("SUPER + X", hl.dsp.exec_cmd("xterm"))\n   \n-- Another comment\n'
    )
    entries = read_keybinds_with_location(conf)
    assert len(entries) == 1
    assert entries[0].key == "X"


# ---------------------------------------------------------------------------
# The shipped bindings.lua — every bind the overlay ships must be one the TUI
# can address (one call per line) and one Omarchy's SUPER+K menu can list (a
# description).
# ---------------------------------------------------------------------------

SHIPPED_KEYBINDS = Path(__file__).resolve().parents[2] / "hypr" / "bindings.lua"

# A bind call at column 0 — the helper's own `  o.bind(keys, description, …)`
# body is indented and must not be counted.
_SHIPPED_CALL_RE = re.compile(r"^(rebind|o\.bind)\(")


def test_shipped_bindings_each_yield_a_described_entry() -> None:
    text = SHIPPED_KEYBINDS.read_text(encoding="utf-8")
    call_lines = [ln for ln in text.splitlines() if _SHIPPED_CALL_RE.match(ln)]
    assert call_lines, "no rebind(/o.bind( calls found in hypr/bindings.lua"

    entries = read_keybinds_with_location(SHIPPED_KEYBINDS)
    assert len(entries) == len(call_lines), (
        f"{len(call_lines)} bind calls in bindings.lua but {len(entries)} parsed"
    )
    for e in entries:
        assert e.description.strip(), f"bind without a description: {e.raw_line.strip()}"
        assert e.call in ("rebind", "o.bind"), e.raw_line
        assert e.key and e.key != "keys", e.raw_line
        assert e.mods.startswith("SUPER"), f"mainMod did not resolve: {e.raw_line.strip()}"
