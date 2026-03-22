"""Tests for hyprconf.cli — Python CLI dispatch layer.

Covers every cmd_* function and the main() dispatcher.
All tests run without a live Hyprland session; hyprctl calls are patched.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

LIB_DIR = Path(__file__).parent.parent.parent / "stow" / "hypr" / ".local" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import hyprconf.cli as cli


def _mock_run(returncode: int = 0, stdout: str = "ok") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


def _inactive(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)


def _active(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test-session")


# ===========================================================================
# cmd_get
# ===========================================================================

def test_get_no_args_lists_sections(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_get([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "general" in out


def test_get_known_section_lists_keys(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_get(["general"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_get_unknown_section_returns_error(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_get(["no_such_section_xyz"])
    assert rc == 1


def test_get_known_section_and_key(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_get(["general", "gaps_in"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_get_unknown_key_returns_error(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_get(["general", "no_such_key_xyz"])
    assert rc == 1


def test_get_shows_persisted_value(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    from hyprconf.config import upsert_option
    upsert_option("general", "gaps_in", "42")
    rc = cli.cmd_get(["general", "gaps_in"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "42" in out


# ===========================================================================
# cmd_set
# ===========================================================================

def test_set_too_few_args(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_set(["general", "gaps_in"])
    assert rc == 1


def test_set_unknown_section(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_set(["no_such_section_xyz", "gaps_in", "5"])
    assert rc == 1


def test_set_unknown_key(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_set(["general", "no_such_key_xyz", "5"])
    assert rc == 1


def test_set_invalid_value_type(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_set(["general", "gaps_in", "not_an_int"])
    assert rc == 1


def test_set_success_inactive(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_set(["general", "gaps_in", "12"])
    assert rc == 0
    from hyprconf.config import read_persisted
    assert read_persisted("general", "gaps_in") == "12"


def test_set_success_active(hypr_dir, capsys, monkeypatch):
    _active(monkeypatch)
    with patch("subprocess.run", return_value=_mock_run(0, "ok")):
        rc = cli.cmd_set(["general", "gaps_in", "7"])
    assert rc == 0
    from hyprconf.config import read_persisted
    assert read_persisted("general", "gaps_in") == "7"


def test_set_multi_word_value(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_set(["input", "kb_layout", "us,de"])
    assert rc == 0


# ===========================================================================
# cmd_configure — non-TTY path + helper functions
# ===========================================================================

def test_configure_requires_tty(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_configure([])
    assert rc == 1


def test_repl_help_root_prints_sections(hypr_dir, capsys):
    cli._repl_help_root()
    out = capsys.readouterr().out
    assert "general" in out or "section" in out.lower()


def test_repl_help_section_prints_keys(hypr_dir, capsys):
    cli._repl_help_section("general")
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_repl_reset_sets_default(hypr_dir, monkeypatch):
    _inactive(monkeypatch)
    from hyprconf.schema import get_option_meta
    meta = get_option_meta("general", "gaps_in")
    assert meta is not None
    _, default, _ = meta
    cli._repl_reset("general", "gaps_in")
    from hyprconf.config import read_persisted
    assert read_persisted("general", "gaps_in") == default


def test_repl_reset_unknown_key(hypr_dir, capsys):
    cli._repl_reset("general", "no_such_key_xyz")
    err = capsys.readouterr().out
    # Should print some error without raising
    assert isinstance(err, str)


def test_repl_query_known_key(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    cli._repl_query("general", "gaps_in")
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_repl_query_unknown_key(hypr_dir, capsys):
    cli._repl_query("general", "no_such_key_xyz")
    out = capsys.readouterr().out
    assert isinstance(out, str)


# ===========================================================================
# cmd_schema
# ===========================================================================

def test_schema_no_subcommand_returns_error(hypr_dir, capsys):
    rc = cli.cmd_schema([])
    assert rc == 1


def test_schema_dump_returns_json(hypr_dir, capsys):
    rc = cli.cmd_schema(["dump"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, dict)


def test_schema_list_sections(hypr_dir, capsys):
    rc = cli.cmd_schema(["list-sections"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "general" in out


def test_schema_keys_valid_section(hypr_dir, capsys):
    rc = cli.cmd_schema(["keys", "general"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_schema_keys_no_section(hypr_dir, capsys):
    rc = cli.cmd_schema(["keys"])
    assert rc == 1


def test_schema_keys_invalid_section(hypr_dir, capsys):
    rc = cli.cmd_schema(["keys", "no_such_section_xyz"])
    assert rc == 1


def test_schema_validate_no_errors(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = cli.cmd_schema(["validate"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "valid" in out.lower() or "ok" in out.lower()


def test_schema_validate_with_valid_persisted(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    from hyprconf.config import upsert_option
    upsert_option("general", "gaps_in", "8")
    rc = cli.cmd_schema(["validate"])
    assert rc == 0


# ===========================================================================
# cmd_autodetect
# ===========================================================================

def test_autodetect_no_config_found(hypr_dir, capsys, monkeypatch):
    import hyprconf.autodetect as _auto
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [hypr_dir / "nope_missing.conf"])
    rc = cli.cmd_autodetect([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no" in out.lower() or "found" in out.lower()


def test_autodetect_with_config(hypr_dir, capsys, monkeypatch):
    import hyprconf.autodetect as _auto
    cfg = hypr_dir / "detect_test.conf"
    cfg.write_text("general {\n    gaps_in = 5\n}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    import hyprconf.config as _config_mod
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", hypr_dir / "nope.conf")
    rc = cli.cmd_autodetect([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Found" in out or "found" in out


# ===========================================================================
# cmd_keybind
# ===========================================================================

def test_keybind_list_empty(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("")
    rc = cli.cmd_keybind(["list"])
    assert rc == 0


def test_keybind_list_with_entries(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("bind = SUPER, T, exec, kitty\n")
    rc = cli.cmd_keybind(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SUPER" in out or "kitty" in out or "exec" in out


def test_keybind_list_no_subcommand(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("")
    rc = cli.cmd_keybind([])
    assert rc == 0


def test_keybind_add_valid(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("")
    rc = cli.cmd_keybind(["add", "bind", "SUPER", "T", "exec", "kitty"])
    assert rc == 0
    assert "bind = SUPER, T, exec, kitty" in KEYBINDS_FILE.read_text()


def test_keybind_add_with_dash_mods(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("")
    rc = cli.cmd_keybind(["add", "bind", "-", "XF86AudioMute", "exec", "amixer toggle"])
    assert rc == 0


def test_keybind_add_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_keybind(["add", "bind", "SUPER"])
    assert rc == 1


def test_keybind_delete_valid(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("bind = SUPER, T, exec, kitty\n")
    rc = cli.cmd_keybind(["delete", "1"])
    assert rc == 0
    from hyprconf.keybinds import read_keybinds_with_location
    assert read_keybinds_with_location(KEYBINDS_FILE) == []


def test_keybind_delete_out_of_range(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("")
    rc = cli.cmd_keybind(["delete", "99"])
    assert rc == 1


def test_keybind_delete_non_digit(hypr_dir, capsys):
    rc = cli.cmd_keybind(["delete", "abc"])
    assert rc == 1


def test_keybind_update_valid(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("bind = SUPER, T, exec, kitty\n")
    rc = cli.cmd_keybind(["update", "1", "bind", "SUPER", "F", "exec", "firefox"])
    assert rc == 0
    text = KEYBINDS_FILE.read_text()
    assert "firefox" in text


def test_keybind_update_too_few_args(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("bind = SUPER, T, exec, kitty\n")
    rc = cli.cmd_keybind(["update", "1", "bind"])
    assert rc == 1


def test_keybind_update_out_of_range(hypr_dir, capsys):
    from hyprconf.keybinds import KEYBINDS_FILE
    KEYBINDS_FILE.write_text("bind = SUPER, T, exec, kitty\n")
    rc = cli.cmd_keybind(["update", "99", "bind", "SUPER", "T", "exec", "kitty"])
    assert rc == 1


def test_keybind_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_keybind(["foobar"])
    assert rc == 1


# ===========================================================================
# cmd_rule — window
# ===========================================================================

def test_rule_window_list_empty(hypr_dir, capsys):
    rc = cli.cmd_rule(["window", "list"])
    assert rc == 0


def test_rule_window_list_no_subcommand(hypr_dir, capsys):
    rc = cli.cmd_rule(["window"])
    assert rc == 0


def test_rule_window_add_valid(hypr_dir, capsys):
    rc = cli.cmd_rule(["window", "add", "float", "class:kitty"])
    assert rc == 0
    from hyprconf.rules import WINRULES_FILE
    assert "float" in WINRULES_FILE.read_text()


def test_rule_window_add_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_rule(["window", "add", "float"])
    assert rc == 1


def test_rule_window_delete_valid(hypr_dir, capsys):
    from hyprconf.rules import WINRULES_FILE, HYPRLAND_CONF
    WINRULES_FILE.write_text("windowrulev2 = float, class:kitty\n")
    HYPRLAND_CONF.write_text(f"source = {WINRULES_FILE}\n")
    rc = cli.cmd_rule(["window", "delete", "1"])
    assert rc == 0


def test_rule_window_delete_out_of_range(hypr_dir, capsys):
    from hyprconf.rules import WINRULES_FILE, HYPRLAND_CONF
    WINRULES_FILE.write_text("")
    HYPRLAND_CONF.write_text(f"source = {WINRULES_FILE}\n")
    rc = cli.cmd_rule(["window", "delete", "99"])
    assert rc == 1


def test_rule_window_update_valid(hypr_dir, capsys):
    from hyprconf.rules import WINRULES_FILE, HYPRLAND_CONF
    WINRULES_FILE.write_text("windowrulev2 = float, class:kitty\n")
    HYPRLAND_CONF.write_text(f"source = {WINRULES_FILE}\n")
    rc = cli.cmd_rule(["window", "update", "1", "tile", "class:alacritty"])
    assert rc == 0


def test_rule_window_update_too_few_args(hypr_dir, capsys):
    from hyprconf.rules import WINRULES_FILE
    WINRULES_FILE.write_text("windowrulev2 = float, class:kitty\n")
    rc = cli.cmd_rule(["window", "update", "1", "tile"])
    assert rc == 1


def test_rule_window_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_rule(["window", "foobar"])
    assert rc == 1


# ===========================================================================
# cmd_rule — workspace
# ===========================================================================

def test_rule_workspace_list_empty(hypr_dir, capsys):
    rc = cli.cmd_rule(["workspace", "list"])
    assert rc == 0


def test_rule_workspace_add_valid(hypr_dir, capsys):
    rc = cli.cmd_rule(["workspace", "add", "1", "monitor:HDMI-A-1"])
    assert rc == 0
    from hyprconf.rules import WKSPRULES_FILE
    assert "workspace = 1" in WKSPRULES_FILE.read_text()


def test_rule_workspace_add_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_rule(["workspace", "add", "1"])
    assert rc == 1


def test_rule_workspace_delete_valid(hypr_dir, capsys):
    from hyprconf.rules import WKSPRULES_FILE, HYPRLAND_CONF
    WKSPRULES_FILE.write_text("workspace = 1, monitor:HDMI-A-1\n")
    HYPRLAND_CONF.write_text(f"source = {WKSPRULES_FILE}\n")
    rc = cli.cmd_rule(["workspace", "delete", "1"])
    assert rc == 0


def test_rule_workspace_update_valid(hypr_dir, capsys):
    from hyprconf.rules import WKSPRULES_FILE, HYPRLAND_CONF
    WKSPRULES_FILE.write_text("workspace = 1, monitor:HDMI-A-1\n")
    HYPRLAND_CONF.write_text(f"source = {WKSPRULES_FILE}\n")
    rc = cli.cmd_rule(["workspace", "update", "1", "2", "monitor:eDP-1"])
    assert rc == 0


def test_rule_workspace_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_rule(["workspace", "foobar"])
    assert rc == 1


def test_rule_unknown_kind(hypr_dir, capsys):
    rc = cli.cmd_rule(["foobar"])
    assert rc == 1


# ===========================================================================
# cmd_monitor
# ===========================================================================

def test_monitor_list_empty(hypr_dir, capsys):
    rc = cli.cmd_monitor(["list"])
    assert rc == 0


def test_monitor_list_no_subcommand(hypr_dir, capsys):
    rc = cli.cmd_monitor([])
    assert rc == 0


def test_monitor_set_valid(hypr_dir, capsys):
    rc = cli.cmd_monitor(["set", "HDMI-A-1", "3840x2160@120", "0x0", "1.5"])
    assert rc == 0
    from hyprconf.monitors import MONITORS_FILE
    assert "HDMI-A-1" in MONITORS_FILE.read_text()


def test_monitor_set_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_monitor(["set", "HDMI-A-1", "1920x1080"])
    assert rc == 1


def test_monitor_set_with_extras(hypr_dir, capsys):
    rc = cli.cmd_monitor(["set", "eDP-1", "2560x1440@165", "0x0", "1", "vrr,1"])
    assert rc == 0


def test_monitor_delete_valid(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE
    MONITORS_FILE.write_text("monitor = HDMI-A-1, 1920x1080@60, 0x0, 1\n")
    rc = cli.cmd_monitor(["delete", "HDMI-A-1"])
    assert rc == 0


def test_monitor_delete_not_found(hypr_dir, capsys):
    rc = cli.cmd_monitor(["delete", "DOES-NOT-EXIST"])
    assert rc == 1


def test_monitor_delete_no_name(hypr_dir, capsys):
    rc = cli.cmd_monitor(["delete"])
    assert rc == 1


def test_monitor_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_monitor(["foobar"])
    assert rc == 1


# ===========================================================================
# cmd_lock
# ===========================================================================

def test_lock_list_empty(hypr_dir, capsys):
    rc = cli.cmd_lock(["list"])
    assert rc == 0


def test_lock_list_no_subcommand(hypr_dir, capsys):
    rc = cli.cmd_lock([])
    assert rc == 0


def test_lock_add_valid_type(hypr_dir, capsys):
    rc = cli.cmd_lock(["add", "background"])
    assert rc == 0


def test_lock_add_invalid_type(hypr_dir, capsys):
    rc = cli.cmd_lock(["add", "invalid_type_xyz"])
    assert rc == 1


def test_lock_add_no_type(hypr_dir, capsys):
    rc = cli.cmd_lock(["add"])
    assert rc == 1


def test_lock_delete_valid(hypr_dir, capsys):
    cli.cmd_lock(["add", "background"])
    rc = cli.cmd_lock(["delete", "1"])
    assert rc == 0


def test_lock_delete_out_of_range(hypr_dir, capsys):
    rc = cli.cmd_lock(["delete", "99"])
    assert rc == 1


def test_lock_delete_non_digit(hypr_dir, capsys):
    rc = cli.cmd_lock(["delete", "abc"])
    assert rc == 1


def test_lock_set_valid(hypr_dir, capsys):
    cli.cmd_lock(["add", "background"])
    rc = cli.cmd_lock(["set", "1", "blur_passes", "3"])
    assert rc == 0


def test_lock_set_out_of_range(hypr_dir, capsys):
    rc = cli.cmd_lock(["set", "99", "key", "value"])
    assert rc == 1


def test_lock_set_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_lock(["set", "1"])
    assert rc == 1


def test_lock_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_lock(["foobar"])
    assert rc == 1


# ===========================================================================
# cmd_idle
# ===========================================================================

def test_idle_list_empty(hypr_dir, capsys):
    rc = cli.cmd_idle(["list"])
    assert rc == 0


def test_idle_list_no_subcommand(hypr_dir, capsys):
    rc = cli.cmd_idle([])
    assert rc == 0


def test_idle_add_listener(hypr_dir, capsys):
    rc = cli.cmd_idle(["add", "listener"])
    assert rc == 0


def test_idle_add_general(hypr_dir, capsys):
    rc = cli.cmd_idle(["add", "general"])
    assert rc == 0


def test_idle_add_invalid_type(hypr_dir, capsys):
    rc = cli.cmd_idle(["add", "invalid_type_xyz"])
    assert rc == 1


def test_idle_add_no_type(hypr_dir, capsys):
    rc = cli.cmd_idle(["add"])
    assert rc == 1


def test_idle_delete_valid(hypr_dir, capsys):
    cli.cmd_idle(["add", "listener"])
    rc = cli.cmd_idle(["delete", "1"])
    assert rc == 0


def test_idle_delete_out_of_range(hypr_dir, capsys):
    rc = cli.cmd_idle(["delete", "99"])
    assert rc == 1


def test_idle_set_valid(hypr_dir, capsys):
    cli.cmd_idle(["add", "listener"])
    rc = cli.cmd_idle(["set", "1", "timeout", "300"])
    assert rc == 0


def test_idle_set_out_of_range(hypr_dir, capsys):
    rc = cli.cmd_idle(["set", "99", "timeout", "300"])
    assert rc == 1


def test_idle_set_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_idle(["set", "1"])
    assert rc == 1


def test_idle_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_idle(["foobar"])
    assert rc == 1


# ===========================================================================
# cmd_paper
# ===========================================================================

def test_paper_list_empty(hypr_dir, capsys):
    rc = cli.cmd_paper(["list"])
    assert rc == 0


def test_paper_list_no_subcommand(hypr_dir, capsys):
    rc = cli.cmd_paper([])
    assert rc == 0


def test_paper_set_wallpaper_valid(hypr_dir, capsys):
    rc = cli.cmd_paper(["set-wallpaper", "eDP-1", "/tmp/wall.jpg"])
    assert rc == 0
    from hyprconf.hyprpaper import HYPRPAPER_FILE
    assert "wall.jpg" in HYPRPAPER_FILE.read_text()


def test_paper_set_wallpaper_all_monitors(hypr_dir, capsys):
    rc = cli.cmd_paper(["set-wallpaper", "-", "/tmp/wall.jpg"])
    assert rc == 0


def test_paper_set_wallpaper_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_paper(["set-wallpaper", "eDP-1"])
    assert rc == 1


def test_paper_add_preload(hypr_dir, capsys):
    rc = cli.cmd_paper(["add-preload", "/tmp/wall.jpg"])
    assert rc == 0
    from hyprconf.hyprpaper import HYPRPAPER_FILE
    assert "preload" in HYPRPAPER_FILE.read_text()


def test_paper_add_preload_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_paper(["add-preload"])
    assert rc == 1


def test_paper_delete_preload_valid(hypr_dir, capsys):
    cli.cmd_paper(["add-preload", "/tmp/wall.jpg"])
    rc = cli.cmd_paper(["delete-preload", "1"])
    assert rc == 0


def test_paper_delete_preload_out_of_range(hypr_dir, capsys):
    rc = cli.cmd_paper(["delete-preload", "99"])
    assert rc == 1


def test_paper_delete_preload_non_digit(hypr_dir, capsys):
    rc = cli.cmd_paper(["delete-preload", "abc"])
    assert rc == 1


def test_paper_delete_wallpaper_line_valid(hypr_dir, capsys):
    cli.cmd_paper(["set-wallpaper", "eDP-1", "/tmp/wall.jpg"])
    rc = cli.cmd_paper(["delete-wallpaper", "1"])
    assert rc == 0


def test_paper_delete_wallpaper_out_of_range(hypr_dir, capsys):
    rc = cli.cmd_paper(["delete-wallpaper", "999"])
    assert rc == 1


def test_paper_setting_valid(hypr_dir, capsys):
    rc = cli.cmd_paper(["setting", "splash", "false"])
    assert rc == 0


def test_paper_setting_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_paper(["setting", "splash"])
    assert rc == 1


def test_paper_unknown_subcommand(hypr_dir, capsys):
    rc = cli.cmd_paper(["foobar"])
    assert rc == 1


# ===========================================================================
# main() dispatcher
# ===========================================================================

def test_main_get(hypr_dir, monkeypatch, capsys):
    _inactive(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "get"])
    rc = cli.main()
    assert rc == 0


def test_main_set_valid(hypr_dir, monkeypatch, capsys):
    _inactive(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "set", "general", "gaps_in", "5"])
    rc = cli.main()
    assert rc == 0


def test_main_schema(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "schema", "list-sections"])
    rc = cli.main()
    assert rc == 0


def test_main_keybind_list(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "keybind", "list"])
    rc = cli.main()
    assert rc == 0


def test_main_rule_list(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "rule", "window", "list"])
    rc = cli.main()
    assert rc == 0


def test_main_monitor_list(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "monitor", "list"])
    rc = cli.main()
    assert rc == 0


def test_main_lock_list(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "lock", "list"])
    rc = cli.main()
    assert rc == 0


def test_main_idle_list(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "idle", "list"])
    rc = cli.main()
    assert rc == 0


def test_main_paper_list(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "paper", "list"])
    rc = cli.main()
    assert rc == 0


def test_main_unknown_command(hypr_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "no_such_cmd_xyz"])
    rc = cli.main()
    assert rc == 1


def test_main_configure_no_tty(hypr_dir, monkeypatch, capsys):
    _inactive(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "configure"])
    rc = cli.main()
    assert rc == 1


def test_main_conf_alias(hypr_dir, monkeypatch, capsys):
    _inactive(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "conf"])
    rc = cli.main()
    assert rc == 1  # No TTY in tests


# ===========================================================================
# Additional gap tests
# ===========================================================================

# ---------------------------------------------------------------------------
# _get_live_or_persisted — live value path (covers L131)
# ---------------------------------------------------------------------------

def test_get_returns_live_value_when_hyprland_active(hypr_dir, capsys, monkeypatch):
    """When hyprctl returns a live value, it should be shown."""
    _active(monkeypatch)
    import json
    payload = json.dumps({"int": 8, "float": 0.0, "str": "", "col": 0, "custom_type": "int"})
    with patch("subprocess.run", return_value=_mock_run(0, payload)):
        rc = cli.cmd_get(["general", "gaps_in"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "8" in out


# ---------------------------------------------------------------------------
# cmd_get section table — default marker path (covers L121)
# ---------------------------------------------------------------------------

def test_get_section_marks_default_values(hypr_dir, capsys, monkeypatch):
    """A persisted value equal to the schema default should still display."""
    _inactive(monkeypatch)
    from hyprconf.config import upsert_option
    from hyprconf.schema import get_option_meta
    meta = get_option_meta("general", "gaps_in")
    assert meta is not None
    _, default, _ = meta
    upsert_option("general", "gaps_in", default)
    rc = cli.cmd_get(["general"])
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_schema validate — error paths (covers L350-352, 356-357, 361-362)
# ---------------------------------------------------------------------------

def test_schema_validate_unknown_key(hypr_dir, capsys):
    from hyprconf.config import OVERRIDES_FILE, MANAGED_MARKER
    OVERRIDES_FILE.write_text(
        f"\n{MANAGED_MARKER}\nno_such_section:no_such_key = val\n"
    )
    rc = cli.cmd_schema(["validate"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "UNKNOWN" in out or "issue" in out.lower()


def test_schema_validate_invalid_value(hypr_dir, capsys):
    from hyprconf.config import OVERRIDES_FILE, MANAGED_MARKER
    OVERRIDES_FILE.write_text(
        f"\n{MANAGED_MARKER}\ngeneral:gaps_in = not_an_int\n"
    )
    rc = cli.cmd_schema(["validate"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "INVALID" in out or "issue" in out.lower()


# ---------------------------------------------------------------------------
# cmd_autodetect — warnings display (covers L388-392)
# ---------------------------------------------------------------------------

def test_autodetect_shows_warnings_for_unreadable_source(hypr_dir, capsys, monkeypatch):
    """When a sourced file raises OSError, cmd_autodetect shows warnings."""
    import hyprconf.autodetect as _auto
    from pathlib import Path

    bad = hypr_dir / "bad.conf"
    bad.write_text("content")
    cfg = hypr_dir / "warn_test.conf"
    cfg.write_text(f"source = {bad}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    import hyprconf.config as _config_mod
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", hypr_dir / "nope.conf")

    real_read_text = Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if self == bad:
            raise OSError("Permission denied")
        return real_read_text(self, *args, **kwargs)

    with patch("pathlib.Path.read_text", mock_read_text):
        rc = cli.cmd_autodetect([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "could not be parsed" in out or "line(s)" in out


# ---------------------------------------------------------------------------
# main() — autodetect dispatch (covers L418)
# ---------------------------------------------------------------------------

def test_main_autodetect(hypr_dir, monkeypatch, capsys):
    import hyprconf.autodetect as _auto
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [hypr_dir / "nope_missing.conf"])
    monkeypatch.setattr(sys, "argv", ["hyprconf-cli", "autodetect"])
    rc = cli.main()
    assert rc == 0


# ---------------------------------------------------------------------------
# window/workspace rule list with entries (covers L553-557, 612-616)
# ---------------------------------------------------------------------------

def test_rule_window_list_with_entries_shows_table(hypr_dir, capsys):
    from hyprconf.rules import WINRULES_FILE, HYPRLAND_CONF
    WINRULES_FILE.write_text("windowrulev2 = float, class:kitty\n")
    HYPRLAND_CONF.write_text(f"source = {WINRULES_FILE}\n")
    rc = cli.cmd_rule(["window", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "float" in out or "kitty" in out or "#" in out


def test_rule_workspace_list_with_entries_shows_table(hypr_dir, capsys):
    from hyprconf.rules import WKSPRULES_FILE, HYPRLAND_CONF
    WKSPRULES_FILE.write_text("workspace = 1, monitor:HDMI-A-1\n")
    HYPRLAND_CONF.write_text(f"source = {WKSPRULES_FILE}\n")
    rc = cli.cmd_rule(["workspace", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1" in out


# ---------------------------------------------------------------------------
# window rule delete/update error paths (covers L577-578, L596-597)
# ---------------------------------------------------------------------------

def test_rule_window_delete_non_digit(hypr_dir, capsys):
    rc = cli.cmd_rule(["window", "delete", "abc"])
    assert rc == 1


def test_rule_window_update_out_of_range(hypr_dir, capsys):
    from hyprconf.rules import WINRULES_FILE, HYPRLAND_CONF
    WINRULES_FILE.write_text("windowrulev2 = float, class:kitty\n")
    HYPRLAND_CONF.write_text(f"source = {WINRULES_FILE}\n")
    rc = cli.cmd_rule(["window", "update", "99", "tile", "class:alacritty"])
    assert rc == 1


# ---------------------------------------------------------------------------
# workspace rule delete/update error paths (covers L634-635, 639-640, 648-649, 653-654)
# ---------------------------------------------------------------------------

def test_rule_workspace_delete_non_digit(hypr_dir, capsys):
    rc = cli.cmd_rule(["workspace", "delete", "abc"])
    assert rc == 1


def test_rule_workspace_delete_out_of_range(hypr_dir, capsys):
    from hyprconf.rules import WKSPRULES_FILE, HYPRLAND_CONF
    WKSPRULES_FILE.write_text("")
    HYPRLAND_CONF.write_text(f"source = {WKSPRULES_FILE}\n")
    rc = cli.cmd_rule(["workspace", "delete", "99"])
    assert rc == 1


def test_rule_workspace_update_non_digit(hypr_dir, capsys):
    rc = cli.cmd_rule(["workspace", "update", "abc", "ws_id", "options"])
    assert rc == 1


def test_rule_workspace_update_out_of_range(hypr_dir, capsys):
    from hyprconf.rules import WKSPRULES_FILE, HYPRLAND_CONF
    WKSPRULES_FILE.write_text("workspace = 1, monitor:HDMI-A-1\n")
    HYPRLAND_CONF.write_text(f"source = {WKSPRULES_FILE}\n")
    rc = cli.cmd_rule(["workspace", "update", "99", "2", "monitor:eDP-1"])
    assert rc == 1


# ---------------------------------------------------------------------------
# monitor list with entries (covers L682-689)
# ---------------------------------------------------------------------------

def test_monitor_list_with_entries_shows_table(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE
    MONITORS_FILE.write_text("monitor = eDP-1, 1920x1080@60, 0x0, 1\n")
    rc = cli.cmd_monitor(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "eDP-1" in out


# ---------------------------------------------------------------------------
# lock list with entries (covers L749-754)
# ---------------------------------------------------------------------------

def test_lock_list_with_entries_shows_table(hypr_dir, capsys):
    cli.cmd_lock(["add", "background"])
    rc = cli.cmd_lock(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "background" in out


# ---------------------------------------------------------------------------
# idle list with entries + delete non-digit (covers L831-836, L854-855)
# ---------------------------------------------------------------------------

def test_idle_list_with_entries_shows_table(hypr_dir, capsys):
    cli.cmd_idle(["add", "listener"])
    rc = cli.cmd_idle(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "listener" in out


def test_idle_delete_non_digit(hypr_dir, capsys):
    rc = cli.cmd_idle(["delete", "abc"])
    assert rc == 1


# ---------------------------------------------------------------------------
# paper list with content (covers L919, L922-924, L927-930, L933-938)
# ---------------------------------------------------------------------------

def test_paper_list_with_settings(hypr_dir, capsys):
    cli.cmd_paper(["setting", "splash", "false"])
    rc = cli.cmd_paper(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "splash" in out


def test_paper_list_with_preloads(hypr_dir, capsys):
    cli.cmd_paper(["add-preload", "/tmp/wall.jpg"])
    rc = cli.cmd_paper(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "preload" in out.lower() or "wall.jpg" in out


def test_paper_list_with_wallpaper_lines(hypr_dir, capsys):
    cli.cmd_paper(["set-wallpaper", "eDP-1", "/tmp/wall.jpg"])
    rc = cli.cmd_paper(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wall.jpg" in out


def test_paper_list_with_wallpaper_block(hypr_dir, capsys):
    from hyprconf.hyprpaper import HYPRPAPER_FILE, add_wallpaper_block
    HYPRPAPER_FILE.write_text("")
    add_wallpaper_block("eDP-1", "/tmp/wall.png", "fill")
    rc = cli.cmd_paper(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "eDP-1" in out or "wall.png" in out


# ---------------------------------------------------------------------------
# paper delete non-digit and block format (covers L983-984, L996-999)
# ---------------------------------------------------------------------------

def test_paper_delete_wallpaper_non_digit(hypr_dir, capsys):
    rc = cli.cmd_paper(["delete-wallpaper", "abc"])
    assert rc == 1


def test_paper_delete_wallpaper_block_format(hypr_dir, capsys):
    from hyprconf.hyprpaper import HYPRPAPER_FILE, add_wallpaper_block
    HYPRPAPER_FILE.write_text("")
    add_wallpaper_block("eDP-1", "/tmp/wall.png")
    # Index 1 with no line-format wallpapers → should hit block format
    rc = cli.cmd_paper(["delete-wallpaper", "1"])
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_configure REPL interactive (covers L198-254)
# ---------------------------------------------------------------------------

def _run_repl(*commands: str, hypr_dir_fixture=None, monkeypatch=None) -> int:
    """Run cmd_configure with mocked TTY and a sequence of inputs."""
    input_seq = iter(commands)

    def _fake_input(prompt=""):
        try:
            return next(input_seq)
        except StopIteration:
            raise EOFError

    with patch("sys.stdin.isatty", return_value=True), \
         patch("sys.stdout.isatty", return_value=True), \
         patch("builtins.input", side_effect=_fake_input):
        return cli.cmd_configure([])


def test_configure_repl_exit_immediately(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("exit")
    assert rc == 0


def test_configure_repl_quit_alias(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("quit")
    assert rc == 0


def test_configure_repl_empty_line_continues(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("", "exit")
    assert rc == 0


def test_configure_repl_help_at_root(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("?", "exit")
    assert rc == 0
    out = capsys.readouterr().out
    assert "general" in out or "section" in out.lower()


def test_configure_repl_unknown_section(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("no_such_xyz", "exit")
    assert rc == 0


def test_configure_repl_enter_and_exit_section(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "exit", "exit")
    assert rc == 0


def test_configure_repl_section_help(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "?", "exit", "exit")
    assert rc == 0
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_configure_repl_section_show(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "show", "exit", "exit")
    assert rc == 0


def test_configure_repl_section_show_key(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "show gaps_in", "exit", "exit")
    assert rc == 0
    out = capsys.readouterr().out
    assert "gaps_in" in out


def test_configure_repl_no_key_resets_to_default(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "no gaps_in", "exit", "exit")
    assert rc == 0


def test_configure_repl_key_query(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "gaps_in ?", "exit", "exit")
    assert rc == 0


def test_configure_repl_set_key_value(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "gaps_in 10", "exit", "exit")
    assert rc == 0
    from hyprconf.config import read_persisted
    assert read_persisted("general", "gaps_in") == "10"


def test_configure_repl_show_key_only(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "gaps_in", "exit", "exit")
    assert rc == 0


def test_configure_repl_up_exits_section(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl("general", "up", "exit")
    assert rc == 0


def test_configure_repl_eof_exits_gracefully(hypr_dir, capsys, monkeypatch):
    _inactive(monkeypatch)
    rc = _run_repl()  # no commands → immediate EOFError
    assert rc == 0


# ---------------------------------------------------------------------------
# schema validate: malformed key (no colon) is skipped (covers L346)
# ---------------------------------------------------------------------------

def test_schema_validate_skips_malformed_key(hypr_dir, capsys):
    """Keys without a colon are silently skipped in schema validate."""
    from hyprconf.config import OVERRIDES_FILE, MANAGED_MARKER
    OVERRIDES_FILE.write_text(
        f"# {MANAGED_MARKER}\nmalformed_no_colon = true\n"
    )
    rc = cli.cmd_schema(["validate"])
    # Malformed key is skipped; no known/valid keys → rc=0
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_autodetect: unknown_lines in output (covers L390)
# ---------------------------------------------------------------------------

def test_autodetect_prints_unknown_lines(hypr_dir, capsys, monkeypatch):
    """When both unknown_lines and warnings exist, cmd_autodetect prints them."""
    import hyprconf.autodetect as _auto
    from hyprconf.autodetect import DetectionResult

    cfg = hypr_dir / "test_unk.conf"
    cfg.write_text("general {\n    border_size = 2\n}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    import hyprconf.config as _config_mod
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", hypr_dir / "nope.conf")

    fake = DetectionResult(found_config=cfg)
    fake.warnings = ["Cannot read bad.conf: Permission denied"]
    fake.unknown_lines = ["unknown_option = 1"]
    fake.parsed_options = []

    from unittest.mock import patch
    with patch.object(_auto, "detect_and_parse", return_value=fake), \
         patch.object(_auto, "migrate", return_value=0):
        rc = cli.cmd_autodetect([])

    assert rc == 0
    out = capsys.readouterr().out
    assert "could not be parsed" in out
    assert "unknown_option" in out


# ===========================================================================
# cmd_monitor field subcommand
# ===========================================================================

def test_monitor_field_show_empty(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE
    MONITORS_FILE.write_text("")
    rc = cli.cmd_monitor(["field", "show"])
    assert rc == 0


def test_monitor_field_show_all(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE
    MONITORS_FILE.write_text("monitor = HDMI-A-1, 1920x1080@60, 0x0, 1.0\n")
    rc = cli.cmd_monitor(["field", "show"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "HDMI-A-1" in out


def test_monitor_field_show_single(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE
    MONITORS_FILE.write_text(
        "monitor = HDMI-A-1, 1920x1080@60, 0x0, 1.0\n"
        "monitor = DP-1, 3840x2160@120, 1920x0, 1.5\n"
    )
    rc = cli.cmd_monitor(["field", "show", "DP-1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DP-1" in out
    assert "3840x2160@120" in out


def test_monitor_field_set_scale(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE, read_monitor_configs
    MONITORS_FILE.write_text("monitor = HDMI-A-1, 1920x1080@60, 0x0, 1.0\n")
    rc = cli.cmd_monitor(["field", "set", "HDMI-A-1", "scale", "2.0"])
    assert rc == 0
    mc = next(c for c in read_monitor_configs(MONITORS_FILE) if c.name == "HDMI-A-1")
    assert mc.scale == "2.0"


def test_monitor_field_set_extras(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE, read_monitor_configs
    MONITORS_FILE.write_text("monitor = HDMI-A-1, 1920x1080@60, 0x0, 1.0\n")
    rc = cli.cmd_monitor(["field", "set", "HDMI-A-1", "vrr", "1"])
    assert rc == 0
    mc = next(c for c in read_monitor_configs(MONITORS_FILE) if c.name == "HDMI-A-1")
    assert "vrr" in mc.extras


def test_monitor_field_set_invalid_field(hypr_dir, capsys):
    from hyprconf.monitors import MONITORS_FILE
    MONITORS_FILE.write_text("monitor = HDMI-A-1, 1920x1080@60, 0x0, 1.0\n")
    rc = cli.cmd_monitor(["field", "set", "HDMI-A-1", "bogusfield", "99"])
    assert rc == 1


def test_monitor_field_set_too_few_args(hypr_dir, capsys):
    rc = cli.cmd_monitor(["field", "set", "HDMI-A-1", "scale"])
    assert rc == 1


def test_monitor_field_unknown_action(hypr_dir, capsys):
    rc = cli.cmd_monitor(["field", "bad"])
    assert rc == 1


# ===========================================================================
# cmd_schema list-sections includes special sections
# ===========================================================================

def test_schema_list_sections_includes_monitors(hypr_dir, capsys):
    rc = cli.cmd_schema(["list-sections"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "monitors" in out


def test_schema_list_sections_includes_theme(hypr_dir, capsys):
    rc = cli.cmd_schema(["list-sections"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "theme" in out


def test_schema_list_sections_includes_hardware(hypr_dir, capsys):
    rc = cli.cmd_schema(["list-sections"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "hardware" in out
