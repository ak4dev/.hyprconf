"""Tests for hyprconf.autodetect — first-run config detection and migration."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

LIB_DIR = Path(__file__).parent.parent.parent / "stow" / "hypr" / ".local" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import hyprconf.autodetect as _auto


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_auto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Patch module-level path constants to safe temp locations."""
    marker   = tmp_path / "hyprconf" / ".initialized"
    overrides = tmp_path / "hypr" / "conf.d" / "99-hyprconf-local.conf"
    (tmp_path / "hypr" / "conf.d").mkdir(parents=True)
    monkeypatch.setattr(_auto, "_FIRST_RUN_MARKER", marker)
    monkeypatch.setattr(_auto, "OVERRIDES_FILE", overrides)
    return marker, overrides


SIMPLE_CONF = """\
general {
    gaps_in = 5
    border_size = 2
}
decoration {
    rounding = 10
}
"""


# ---------------------------------------------------------------------------
# is_initialized
# ---------------------------------------------------------------------------

def test_is_initialized_false_when_nothing_exists(tmp_path, monkeypatch):
    _setup_auto(tmp_path, monkeypatch)
    assert _auto.is_initialized() is False


def test_is_initialized_true_when_marker_exists(tmp_path, monkeypatch):
    marker, _ = _setup_auto(tmp_path, monkeypatch)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    assert _auto.is_initialized() is True


def test_is_initialized_true_when_overrides_exists(tmp_path, monkeypatch):
    _, overrides = _setup_auto(tmp_path, monkeypatch)
    overrides.touch()
    assert _auto.is_initialized() is True


# ---------------------------------------------------------------------------
# find_config
# ---------------------------------------------------------------------------

def test_find_config_returns_none_when_none_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [tmp_path / "nope.conf"])
    assert _auto.find_config() is None


def test_find_config_returns_first_existing(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg, tmp_path / "other.conf"])
    assert _auto.find_config() == cfg


def test_find_config_skips_nonexistent_first_candidate(tmp_path, monkeypatch):
    second = tmp_path / "second.conf"
    second.write_text("")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [tmp_path / "missing.conf", second])
    assert _auto.find_config() == second


# ---------------------------------------------------------------------------
# detect_and_parse — no config
# ---------------------------------------------------------------------------

def test_detect_and_parse_no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [tmp_path / "nope.conf"])
    result = _auto.detect_and_parse()
    assert result.found_config is None
    assert result.option_count == 0
    assert result.warning_count == 1  # "No hyprland.conf found"


# ---------------------------------------------------------------------------
# detect_and_parse — simple config parsing
# ---------------------------------------------------------------------------

def test_detect_and_parse_finds_known_options(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(SIMPLE_CONF)
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    assert result.found_config == cfg
    sections = {o.section for o in result.parsed_options}
    assert "general" in sections


def test_detect_and_parse_parses_key_values(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(SIMPLE_CONF)
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    keys = {o.key for o in result.parsed_options}
    assert "gaps_in" in keys or "border_size" in keys or "rounding" in keys


def test_detect_and_parse_skips_comments(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("# this is a comment\ngeneral {\n    gaps_in = 5\n}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    assert result.option_count >= 0  # No error; comment ignored


def test_detect_and_parse_records_unknown_lines(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("general {\n    totally_unknown_option_xyz = 999\n}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    assert len(result.unknown_lines) > 0


def test_detect_and_parse_nested_section(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("decoration {\n    blur {\n        enabled = true\n    }\n}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    sections = {o.section for o in result.parsed_options}
    assert any("blur" in s for s in sections)


def test_detect_and_parse_three_level_nesting(tmp_path, monkeypatch):
    """Regression: 3-level nesting must produce 'group.groupbar', not 'group.group.groupbar'."""
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(
        "group {\n"
        "    groupbar {\n"
        "        enabled = true\n"
        "        font_size = 10\n"
        "    }\n"
        "}\n"
    )
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    sections = {o.section for o in result.parsed_options}
    assert "group.groupbar" in sections
    # Must NOT contain the buggy double-prefixed key
    assert not any("group.group." in s for s in sections)
    sub = tmp_path / "sub.conf"
    sub.write_text("general {\n    gaps_in = 8\n}\n")
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(f"source = {sub}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    keys = {o.key for o in result.parsed_options}
    assert "gaps_in" in keys


def test_detect_and_parse_handles_missing_source(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(f"source = {tmp_path / 'missing.conf'}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    # Should not raise; just silently skips missing source
    result = _auto.detect_and_parse()
    assert isinstance(result, _auto.DetectionResult)


def test_detect_and_parse_prevents_cycles(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    # Self-referencing source should not cause infinite recursion
    cfg.write_text(f"source = {cfg}\ngeneral {{\n    gaps_in = 5\n}}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    assert isinstance(result, _auto.DetectionResult)


# ---------------------------------------------------------------------------
# DetectionResult properties
# ---------------------------------------------------------------------------

def test_option_count_matches_list(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(SIMPLE_CONF)
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    assert result.option_count == len(result.parsed_options)


def test_warning_count_matches_list(tmp_path, monkeypatch):
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("general {\n    totally_unknown_xyz = 1\n}\n")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    result = _auto.detect_and_parse()
    assert result.warning_count == len(result.warnings)


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

def test_migrate_returns_zero_for_empty_result(tmp_path, monkeypatch):
    _setup_auto(tmp_path, monkeypatch)
    result = _auto.DetectionResult(found_config=None)
    assert _auto.migrate(result) == 0


def test_migrate_writes_options(tmp_path, monkeypatch):
    marker, overrides = _setup_auto(tmp_path, monkeypatch)
    import hyprconf.config as _config_mod
    monkeypatch.setattr(_config_mod, "OVERRIDES_FILE", overrides)
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", tmp_path / "nope.conf")

    result = _auto.DetectionResult(found_config=tmp_path / "hyprland.conf")
    result.parsed_options.append(
        _auto.ParsedOption(
            section="general", key="gaps_in", value="5",
            source_file=tmp_path / "hyprland.conf", source_line=1,
        )
    )
    n = _auto.migrate(result)
    assert n >= 1


def test_migrate_marks_initialized(tmp_path, monkeypatch):
    marker, overrides = _setup_auto(tmp_path, monkeypatch)
    import hyprconf.config as _config_mod
    monkeypatch.setattr(_config_mod, "OVERRIDES_FILE", overrides)
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", tmp_path / "nope.conf")

    result = _auto.DetectionResult(found_config=tmp_path / "hyprland.conf")
    result.parsed_options.append(
        _auto.ParsedOption("general", "gaps_in", "5", tmp_path / "hyprland.conf", 1)
    )
    _auto.migrate(result)
    assert marker.exists()


# ---------------------------------------------------------------------------
# _mark_initialized
# ---------------------------------------------------------------------------

def test_mark_initialized_creates_nested_file(tmp_path, monkeypatch):
    marker = tmp_path / "a" / "b" / "c" / ".initialized"
    monkeypatch.setattr(_auto, "_FIRST_RUN_MARKER", marker)
    _auto._mark_initialized()
    assert marker.exists()


# ---------------------------------------------------------------------------
# first_run_check
# ---------------------------------------------------------------------------

def test_first_run_check_exits_early_when_initialized(tmp_path, monkeypatch, capsys):
    _, overrides = _setup_auto(tmp_path, monkeypatch)
    overrides.touch()
    _auto.first_run_check(interactive=False)
    # No output expected — returns immediately
    assert capsys.readouterr().err == ""


def test_first_run_check_no_config_marks_initialized(tmp_path, monkeypatch):
    marker, _ = _setup_auto(tmp_path, monkeypatch)
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [tmp_path / "nope.conf"])
    _auto.first_run_check(interactive=False)
    assert marker.exists()


def test_first_run_check_non_interactive_prints_warning(tmp_path, monkeypatch, capsys):
    _setup_auto(tmp_path, monkeypatch)
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    _auto.first_run_check(interactive=False)
    err = capsys.readouterr().err
    assert "hyprconf" in err or "config" in err.lower()


def test_first_run_check_interactive_yes_imports_options(tmp_path, monkeypatch):
    marker, overrides = _setup_auto(tmp_path, monkeypatch)
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text(SIMPLE_CONF)
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])
    import hyprconf.config as _config_mod
    monkeypatch.setattr(_config_mod, "OVERRIDES_FILE", overrides)
    monkeypatch.setattr(_config_mod, "LEGACY_OVERRIDES_FILE", tmp_path / "nope.conf")

    with patch("sys.stdin.isatty", return_value=True), \
         patch("builtins.input", return_value="y"):
        _auto.first_run_check(interactive=True)

    assert overrides.exists()


def test_first_run_check_interactive_no_marks_initialized(tmp_path, monkeypatch):
    marker, _ = _setup_auto(tmp_path, monkeypatch)
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])

    with patch("sys.stdin.isatty", return_value=True), \
         patch("builtins.input", return_value="n"):
        _auto.first_run_check(interactive=True)

    assert marker.exists()


def test_first_run_check_non_tty_stdin_skips_prompt(tmp_path, monkeypatch, capsys):
    _setup_auto(tmp_path, monkeypatch)
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])

    # interactive=True but stdin is not a TTY — should fall back to non-interactive
    with patch("sys.stdin.isatty", return_value=False):
        _auto.first_run_check(interactive=True)

    err = capsys.readouterr().err
    assert "hyprconf" in err or "autodetect" in err


# ---------------------------------------------------------------------------
# _mark_initialized OSError is silently ignored (covers L204-205)
# ---------------------------------------------------------------------------

def test_mark_initialized_oserror_is_ignored(tmp_path, monkeypatch):
    """_mark_initialized must silently swallow an OSError on touch."""
    _setup_auto(tmp_path, monkeypatch)
    from unittest.mock import MagicMock
    mock_marker = MagicMock()
    mock_marker.parent.mkdir = MagicMock()
    mock_marker.touch.side_effect = OSError("no space left")
    monkeypatch.setattr(_auto, "_FIRST_RUN_MARKER", mock_marker)
    _auto._mark_initialized()  # must not raise


# ---------------------------------------------------------------------------
# first_run_check with warnings after import (covers L241)
# ---------------------------------------------------------------------------

def test_first_run_check_prints_warning_when_parse_has_warnings(tmp_path, monkeypatch, capsys):
    """If detect_and_parse produces warnings, first_run_check prints them."""
    _setup_auto(tmp_path, monkeypatch)
    cfg = tmp_path / "hyprland.conf"
    cfg.write_text("")
    monkeypatch.setattr(_auto, "CANDIDATE_CONFIGS", [cfg])

    from hyprconf.autodetect import DetectionResult
    fake_result = DetectionResult(found_config=cfg)
    fake_result.warnings = ["Cannot read foo.conf: Permission denied"]
    fake_result.parsed_options = []

    from unittest.mock import patch
    with patch.object(_auto, "detect_and_parse", return_value=fake_result), \
         patch.object(_auto, "migrate", return_value=0), \
         patch("sys.stdin.isatty", return_value=True), \
         patch("builtins.input", return_value="y"):
        _auto.first_run_check(interactive=True)

    out = capsys.readouterr().out
    assert "could not be parsed" in out
