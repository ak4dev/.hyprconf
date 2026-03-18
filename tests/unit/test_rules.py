"""Tests for hyprconf.rules — window and workspace rule parser/writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from hyprconf.rules import (
    RuleEntry,
    add_window_rule,
    add_workspace_rule,
    delete_rule,
    read_window_rules,
    read_window_rules_with_location,
    read_workspace_rules,
    read_workspace_rules_with_location,
    update_window_rule,
    update_workspace_rule,
)

HYPRLAND_CONF = """\
windowrulev2 = float, class:Alacritty
windowrulev2 = size 800 600, class:Alacritty
windowrule = tile, class:spotify
workspace = 1, monitor:HDMI-A-1, default:true
workspace = special:magic, on-created-empty:kitty
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hypr_conf(hypr_dir: Path, content: str) -> Path:
    p = hypr_dir / "hyprland.conf"
    p.write_text(content)
    return p


def _win_rules_file(hypr_dir: Path, content: str = "") -> Path:
    p = hypr_dir / "conf.d" / "50-windowrules.conf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _wksp_rules_file(hypr_dir: Path, content: str = "") -> Path:
    p = hypr_dir / "conf.d" / "50-workspacerules.conf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_window_rules_with_location
# ---------------------------------------------------------------------------

def test_reads_window_rules(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    entries = read_window_rules_with_location(p)
    assert len(entries) == 3


def test_window_rule_text(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    entries = read_window_rules_with_location(p)
    rules = [e.rule for e in entries]
    assert any("float" in r and "Alacritty" in r for r in rules)


def test_window_rule_line_idx(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    entries = read_window_rules_with_location(p)
    for e in entries:
        assert e.file_path == p
        assert e.line_idx >= 0


def test_empty_file_returns_empty(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, "")
    assert read_window_rules_with_location(p) == []


def test_ignores_comments(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, "# windowrulev2 = float, class:X\nwindowrulev2 = tile, class:Y\n")
    entries = read_window_rules_with_location(p)
    assert len(entries) == 1
    assert "class:Y" in entries[0].rule


def test_read_window_rules_simple_list(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    rules = read_window_rules(p)
    assert isinstance(rules, list)
    assert all(isinstance(r, str) for r in rules)


# ---------------------------------------------------------------------------
# read_workspace_rules_with_location
# ---------------------------------------------------------------------------

def test_reads_workspace_rules(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    entries = read_workspace_rules_with_location(p)
    assert len(entries) == 2


def test_workspace_rule_text(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    entries = read_workspace_rules_with_location(p)
    rules = [e.rule for e in entries]
    assert any("monitor:HDMI-A-1" in r for r in rules)


def test_read_workspace_rules_simple_list(hypr_dir: Path) -> None:
    p = _hypr_conf(hypr_dir, HYPRLAND_CONF)
    rules = read_workspace_rules(p)
    assert isinstance(rules, list)
    assert len(rules) == 2


# ---------------------------------------------------------------------------
# add_window_rule
# ---------------------------------------------------------------------------

def test_add_window_rule_appends(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    assert add_window_rule("float", ["class:MyApp"], file=p) is True
    entries = read_window_rules_with_location(p)
    assert len(entries) == 1
    assert "float" in entries[0].rule
    assert "class:MyApp" in entries[0].rule


def test_add_window_rule_multiple_filters(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", ["class:Alacritty", "title:.*Edit.*"], file=p)
    entries = read_window_rules_with_location(p)
    assert "class:Alacritty" in entries[0].rule
    assert "title:.*Edit.*" in entries[0].rule


def test_add_window_rule_no_filters(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", [], file=p)
    entries = read_window_rules_with_location(p)
    assert "windowrulev2 = float" in entries[0].rule


def test_add_window_rule_format(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", ["class:X"], file=p)
    text = p.read_text()
    assert "windowrulev2 = float, class:X" in text


# ---------------------------------------------------------------------------
# add_workspace_rule
# ---------------------------------------------------------------------------

def test_add_workspace_rule(hypr_dir: Path) -> None:
    p = _wksp_rules_file(hypr_dir)
    assert add_workspace_rule("1", "monitor:HDMI-A-1, default:true", file=p) is True
    entries = read_workspace_rules_with_location(p)
    assert len(entries) == 1
    assert "monitor:HDMI-A-1" in entries[0].rule


def test_add_workspace_rule_no_options(hypr_dir: Path) -> None:
    p = _wksp_rules_file(hypr_dir)
    add_workspace_rule("special:magic", "", file=p)
    text = p.read_text()
    assert "workspace = special:magic" in text


# ---------------------------------------------------------------------------
# delete_rule
# ---------------------------------------------------------------------------

def test_delete_window_rule(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir, "windowrulev2 = float, class:X\nwindowrulev2 = tile, class:Y\n")
    entries = read_window_rules_with_location(p)
    first = entries[0]
    assert delete_rule(first.file_path, first.line_idx) is True
    remaining = read_window_rules_with_location(p)
    assert len(remaining) == 1
    assert "class:Y" in remaining[0].rule


def test_delete_rule_invalid_idx(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir, "windowrulev2 = float, class:X\n")
    assert delete_rule(p, 999) is False


# ---------------------------------------------------------------------------
# update_window_rule
# ---------------------------------------------------------------------------

def test_update_window_rule(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir, "windowrulev2 = float, class:X\n")
    entries = read_window_rules_with_location(p)
    e = entries[0]
    assert update_window_rule(e.file_path, e.line_idx, "tile", ["class:X"]) is True
    updated = read_window_rules_with_location(p)
    assert "tile" in updated[0].rule


# ---------------------------------------------------------------------------
# update_workspace_rule
# ---------------------------------------------------------------------------

def test_update_workspace_rule(hypr_dir: Path) -> None:
    p = _wksp_rules_file(hypr_dir, "workspace = 1, monitor:DP-1\n")
    entries = read_workspace_rules_with_location(p)
    e = entries[0]
    assert update_workspace_rule(e.file_path, e.line_idx, "1", "monitor:HDMI-A-1") is True
    updated = read_workspace_rules_with_location(p)
    assert "monitor:HDMI-A-1" in updated[0].rule


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_window_rule_crud_round_trip(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)

    add_window_rule("float", ["class:TestApp"], file=p)
    entries = read_window_rules_with_location(p)
    assert len(entries) == 1
    e = entries[0]

    update_window_rule(e.file_path, e.line_idx, "tile", ["class:TestApp"])
    entries = read_window_rules_with_location(p)
    assert "tile" in entries[0].rule

    delete_rule(entries[0].file_path, entries[0].line_idx)
    assert read_window_rules_with_location(p) == []
