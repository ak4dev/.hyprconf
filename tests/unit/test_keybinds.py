"""Tests for hyprconf.keybinds — keybind parser and writer."""

from __future__ import annotations

from pathlib import Path

from hyprconf.keybinds import (
    add_keybind,
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
# update_keybind
# ---------------------------------------------------------------------------


def test_update_keybind_changes_args(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location(p)
    e = entries[0]
    assert (
        update_keybind(e.file_path, e.line_idx, "bind", "SUPER", "T", "exec", "alacritty") is True
    )
    updated = read_keybinds_with_location(p)
    assert updated[0].args == "alacritty"


def test_update_keybind_changes_kind(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location(p)
    e = entries[0]
    update_keybind(e.file_path, e.line_idx, "binde", "SUPER", "T", "exec", "kitty")
    updated = read_keybinds_with_location(p)
    assert updated[0].kind == "binde"


def test_update_keybind_invalid_idx(hypr_dir: Path) -> None:
    p = hypr_dir / "keybinds.conf"
    p.write_text("bind = SUPER, T, exec, kitty\n")
    assert update_keybind(p, 999, "bind", "SUPER", "T", "exec", "kitty") is False


# ---------------------------------------------------------------------------
# Default path (covers L75 — KEYBINDS_FILE default in read_keybinds_with_location)
# ---------------------------------------------------------------------------


def test_read_keybinds_with_location_uses_default_path(hypr_dir: Path) -> None:
    """Calling without a file arg should use KEYBINDS_FILE."""
    from hyprconf.keybinds import KEYBINDS_FILE, read_keybinds_with_location

    KEYBINDS_FILE.write_text("bind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location()  # no file arg → uses KEYBINDS_FILE
    assert len(entries) == 1
    assert entries[0].dispatcher == "exec"


# ---------------------------------------------------------------------------
# add_keybind default path (covers L153)
# ---------------------------------------------------------------------------


def test_add_keybind_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.keybinds import KEYBINDS_FILE, add_keybind, read_keybinds_with_location

    KEYBINDS_FILE.write_text("")
    add_keybind("bind", "SUPER", "F", "exec", "firefox")  # no file arg
    entries = read_keybinds_with_location(KEYBINDS_FILE)
    assert len(entries) == 1


# ---------------------------------------------------------------------------
# Source file following (covers L95-103)
# ---------------------------------------------------------------------------


def test_read_follows_source_include(hypr_dir: Path) -> None:
    sub = hypr_dir / "extra_keybinds.conf"
    sub.write_text("bind = SUPER, E, exec, nemo\n")
    main_kb = hypr_dir / "keybinds.conf"
    main_kb.write_text(f"source = {sub}\nbind = SUPER, T, exec, kitty\n")
    entries = read_keybinds_with_location(main_kb, follow_sources=True)
    dispatchers = {e.dispatcher for e in entries}
    assert "exec" in dispatchers
    assert len(entries) == 2


# ---------------------------------------------------------------------------
# Source following with glob pattern (covers L99-100)
# ---------------------------------------------------------------------------


def test_read_follows_glob_source(hypr_dir: Path) -> None:
    """read_keybinds_with_location follows glob patterns in source= lines."""
    from hyprconf.keybinds import read_keybinds_with_location

    kb_dir = hypr_dir / "keys.d"
    kb_dir.mkdir()
    (kb_dir / "a.conf").write_text("bind = SUPER, A, exec, app1\n")
    (kb_dir / "b.conf").write_text("bind = SUPER, B, exec, app2\n")
    main_kb = hypr_dir / "keybinds.conf"
    main_kb.write_text(f"source = {kb_dir}/*.conf\n")
    entries = read_keybinds_with_location(main_kb, follow_sources=True)
    dispatchers = {e.dispatcher for e in entries}
    assert "exec" in dispatchers
    assert len(entries) == 2


# ---------------------------------------------------------------------------
# Edge cases: malformed input
# ---------------------------------------------------------------------------


def test_read_keybinds_malformed_lines(hypr_dir: Path) -> None:
    """Lines with wrong field count or no = are skipped gracefully."""
    conf = hypr_dir / "keybinds.conf"
    conf.write_text(
        "$mainMod = SUPER\n"
        "bind = $mainMod, T, exec, kitty\n"
        "this is not a keybind line\n"
        "bind = \n"
        "bind $mainMod SHIFT Q killactive\n"
        "bind = $mainMod, R, exec, rofi\n"
    )
    entries = read_keybinds_with_location(conf)
    assert len(entries) == 2
    assert entries[0].key == "T"
    assert entries[1].key == "R"


def test_read_keybinds_blank_and_comment_lines(hypr_dir: Path) -> None:
    """Blank lines and comments are ignored."""
    conf = hypr_dir / "keybinds.conf"
    conf.write_text(
        "\n\n# This is a comment\nbind = SUPER, X, exec, xterm\n   \n# Another comment\n"
    )
    entries = read_keybinds_with_location(conf)
    assert len(entries) == 1
    assert entries[0].key == "X"


def test_read_keybinds_relative_source(tmp_path: Path) -> None:
    """A relative `source = ./foo.conf` resolves against the including file's dir."""
    from hyprconf.keybinds import read_keybinds_with_location

    sub = tmp_path / "extra.conf"
    sub.write_text("bind = SUPER, X, exec, foo\n")
    main = tmp_path / "hyprland.conf"
    main.write_text("source = extra.conf\n")
    entries = read_keybinds_with_location(main, follow_sources=True)
    assert any(e.key == "X" and e.dispatcher == "exec" for e in entries)
