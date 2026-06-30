"""Tests for hyprconf.rules — window and workspace rule parser/writer."""

from __future__ import annotations

from pathlib import Path

from hyprconf.rules import (
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
    assert "match:class MyApp" in entries[0].rule


def test_add_window_rule_multiple_filters(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", ["class:Alacritty", "title:.*Edit.*"], file=p)
    entries = read_window_rules_with_location(p)
    assert "match:class Alacritty" in entries[0].rule
    assert "match:title .*Edit.*" in entries[0].rule


def test_add_window_rule_no_filters(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", [], file=p)
    entries = read_window_rules_with_location(p)
    assert "windowrule = float on" in entries[0].rule


def test_add_window_rule_format(hypr_dir: Path) -> None:
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", ["class:X"], file=p)
    text = p.read_text()
    assert "windowrule = float on, match:class X" in text


def test_add_window_rule_never_writes_deprecated_v2(hypr_dir: Path) -> None:
    """Hyprland 0.55 rejects ``windowrulev2``; the writer must never emit it."""
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", ["class:X"], file=p)
    add_window_rule("size 800 600", ["floating:1", "title:.*"], file=p)
    assert "windowrulev2" not in p.read_text()


def test_add_window_rule_renames_legacy_filter_fields(hypr_dir: Path) -> None:
    """Legacy v2 field names are mapped to current ``match:`` props."""
    p = _win_rules_file(hypr_dir)
    add_window_rule("float", ["floating:1"], file=p)
    text = p.read_text()
    assert "match:float 1" in text
    assert "floating:" not in text


def test_compose_window_rule_keeps_valued_effect(hypr_dir: Path) -> None:
    """An effect that already carries a value is not given a spurious ``on``."""
    from hyprconf.rules import compose_window_rule

    line = compose_window_rule("size 800 600", ["class:X"])
    assert line == "windowrule = size 800 600, match:class X"


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


# ---------------------------------------------------------------------------
# Source file following (covers L71-77 in rules.py _collect_rules)
# ---------------------------------------------------------------------------


def test_collect_rules_follows_source_include(hypr_dir: Path) -> None:
    from hyprconf.rules import HYPRLAND_CONF, read_window_rules_with_location

    sub = hypr_dir / "extra_rules.conf"
    sub.write_text("windowrulev2 = float, class:extra\n")
    HYPRLAND_CONF.write_text(f"source = {sub}\nwindowrulev2 = float, class:main\n")
    entries = read_window_rules_with_location(HYPRLAND_CONF)
    classes = " ".join(e.rule for e in entries)
    assert "extra" in classes
    assert "main" in classes


# ---------------------------------------------------------------------------
# add_window_rule default path (covers L112)
# ---------------------------------------------------------------------------


def test_add_window_rule_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.rules import WINRULES_FILE, add_window_rule

    WINRULES_FILE.write_text("")
    add_window_rule("float", ["class:default_test"])  # no file arg
    assert "float" in WINRULES_FILE.read_text()


# ---------------------------------------------------------------------------
# add_workspace_rule default path (covers L128)
# ---------------------------------------------------------------------------


def test_add_workspace_rule_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.rules import WKSPRULES_FILE, add_workspace_rule

    WKSPRULES_FILE.write_text("")
    add_workspace_rule("1", "monitor:HDMI-A-1")  # no file arg
    assert "workspace = 1" in WKSPRULES_FILE.read_text()


# ---------------------------------------------------------------------------
# _collect_rules: source pointing to non-existent file is silently skipped
# (covers L62: not p.exists() → return early)
# ---------------------------------------------------------------------------


def test_collect_rules_skips_nonexistent_source(hypr_dir: Path) -> None:
    from hyprconf.rules import HYPRLAND_CONF, WINRULES_FILE

    # Set up hyprland.conf sourcing a non-existent file
    nonexistent = hypr_dir / "no_such.conf"
    HYPRLAND_CONF.write_text(f"source = {nonexistent}\n")
    WINRULES_FILE.write_text("")
    from hyprconf.rules import read_window_rules_with_location

    # Should return empty without raising
    entries = read_window_rules_with_location()
    assert entries == []


# ---------------------------------------------------------------------------
# _collect_rules: glob source pattern expands matches (covers L73-74)
# ---------------------------------------------------------------------------


def test_collect_rules_follows_glob_source(hypr_dir: Path) -> None:
    from hyprconf.rules import HYPRLAND_CONF, read_window_rules_with_location

    # Create two rule files matched by a glob
    rules_dir = hypr_dir / "rules.d"
    rules_dir.mkdir()
    (rules_dir / "01.conf").write_text("windowrule = float, class:app1\n")
    (rules_dir / "02.conf").write_text("windowrule = tile, class:app2\n")
    HYPRLAND_CONF.write_text(f"source = {rules_dir}/*.conf\n")
    entries = read_window_rules_with_location()
    dispatchers = {e.rule for e in entries}
    assert any("app1" in d for d in dispatchers)
    assert any("app2" in d for d in dispatchers)


def test_collect_rules_resolves_relative_source(hypr_dir: Path) -> None:
    """A relative `source = ./extra.conf` resolves against the including file's dir."""
    from hyprconf.rules import HYPRLAND_CONF, read_window_rules_with_location

    extra = hypr_dir / "extra.conf"
    extra.write_text("windowrule = float, class:relApp\n")
    HYPRLAND_CONF.write_text("source = extra.conf\n")
    entries = read_window_rules_with_location()
    assert any("relApp" in e.rule for e in entries)
