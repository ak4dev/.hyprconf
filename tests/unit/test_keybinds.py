"""Tests for hyprconf.keybinds — keybind parser and writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from hyprconf.keybinds import (
    KeybindEntry,
    add_keybind,
    delete_keybind,
    read_keybinds,
    read_keybinds_with_location,
    update_keybind,
)

KEYBINDS_CONF = """\
$mainMod = SUPER
bind = $mainMod, T, exec, kitty
bind = $mainMod SHIFT, Q, killactive,
bindl = , XF86AudioPlay, exec, playerctl play-pause
bindel = , XF86MonBrightnessUp, exec, brightnessctl set 5%+
bindm = $mainMod, mouse:272, movewindow
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kb_file(hypr_dir: Path, content: str = KEYBINDS_CONF) -> Path:
    p = hypr_dir / "keybinds.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_keybinds_with_location
# ---------------------------------------------------------------------------

def test_reads_basic_bind(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.conf")
    kinds = {e.kind for e in entries}
    assert "bind" in kinds


def test_reads_all_bind_kinds(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.conf")
    kinds = {e.kind for e in entries}
    assert kinds == {"bind", "bindl", "bindel", "bindm"}


def test_variable_expansion(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.conf")
    # $mainMod should be expanded to SUPER
    mod_entries = [e for e in entries if "SUPER" in e.mods]
    assert len(mod_entries) >= 3


def test_entry_fields(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.conf")
    kitty_entry = next(e for e in entries if e.dispatcher == "exec" and "kitty" in e.args)
    assert kitty_entry.key == "T"
    assert kitty_entry.mods == "SUPER"
    assert kitty_entry.kind == "bind"


def test_raw_line_preserved(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    entries = read_keybinds_with_location(hypr_dir / "keybinds.conf")
    for e in entries:
        assert "$mainMod" in e.raw_line or e.kind in ("bindl", "bindel", "bindm")


def test_line_idx_correct(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    p = hypr_dir / "keybinds.conf"
    entries = read_keybinds_with_location(p)
    for entry in entries:
        assert entry.file_path == p
        assert entry.line_idx >= 0
        lines = p.read_text().splitlines()
        assert entry.line_idx < len(lines)


def test_empty_file(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("")
    assert read_keybinds_with_location(p) == []


def test_missing_file(hypr_dir: Path) -> None:
    p = hypr_dir / "nonexistent.conf"
    assert read_keybinds_with_location(p) == []


def test_ignores_comments(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("# bind = SUPER, X, exec, foo\nbind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    assert entries[0].args == "kitty"


def test_read_keybinds_simple_tuples(hypr_dir: Path) -> None:
    _kb_file(hypr_dir)
    result = read_keybinds(hypr_dir / "keybinds.conf")
    assert isinstance(result, list)
    assert all(len(t) == 5 for t in result)


# ---------------------------------------------------------------------------
# add_keybind
# ---------------------------------------------------------------------------

def test_add_keybind_appends(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("")
    assert add_keybind("bind", "SUPER", "F", "exec", "firefox", file=p) is True
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    assert entries[0].key == "F"
    assert entries[0].args == "firefox"


def test_add_keybind_preserves_existing(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    add_keybind("bind", "SUPER", "F", "exec", "firefox", file=p)
    entries = read_keybinds_with_location(p)
    assert len(entries) == 2


def test_add_keybind_formats_correctly(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("")
    add_keybind("bindl", "", "XF86AudioPlay", "exec", "playerctl play-pause", file=p)
    text = p.read_text()
    assert "bindl = , XF86AudioPlay, exec, playerctl play-pause" in text


# ---------------------------------------------------------------------------
# delete_keybind
# ---------------------------------------------------------------------------

def test_delete_keybind(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\nbind = SUPER, F, exec, firefox\n")
    entries = read_keybinds_with_location(p)
    first = entries[0]
    assert delete_keybind(first.file_path, first.line_idx) is True
    remaining = read_keybinds_with_location(p)
    assert len(remaining) == 1
    assert remaining[0].args == "firefox"


def test_delete_keybind_invalid_idx(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    assert delete_keybind(p, 999) is False


# ---------------------------------------------------------------------------
# update_keybind
# ---------------------------------------------------------------------------

def test_update_keybind_changes_args(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location(p)
    e = entries[0]
    assert update_keybind(e.file_path, e.line_idx,
                          "bind", "SUPER", "T", "exec", "alacritty") is True
    updated = read_keybinds_with_location(p)
    assert updated[0].args == "alacritty"


def test_update_keybind_changes_kind(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location(p)
    e = entries[0]
    update_keybind(e.file_path, e.line_idx,
                   "binde", "SUPER", "T", "exec", "kitty")
    updated = read_keybinds_with_location(p)
    assert updated[0].kind == "binde"


def test_update_keybind_invalid_idx(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    assert update_keybind(p, 999, "bind", "SUPER", "T", "exec", "kitty") is False


# ---------------------------------------------------------------------------
# Round-trip: add → read → update → read → delete → read
# ---------------------------------------------------------------------------

def test_full_crud_round_trip(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("")

    # Add
    add_keybind("bind", "SUPER", "G", "exec", "nautilus", file=p)
    entries = read_keybinds_with_location(p)
    assert len(entries) == 1
    e = entries[0]

    # Update
    update_keybind(e.file_path, e.line_idx, "bind", "SUPER", "G", "exec", "thunar")
    entries = read_keybinds_with_location(p)
    assert entries[0].args == "thunar"

    # Delete
    delete_keybind(entries[0].file_path, entries[0].line_idx)
    assert read_keybinds_with_location(p) == []
