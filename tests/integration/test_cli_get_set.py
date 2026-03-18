"""
Integration tests for hyprconf CLI — get / set / configure commands.

These tests exercise the Python CLI layer with hyprctl subprocess calls
mocked, so no running Hyprland session is required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

LIB_DIR = Path(__file__).parent.parent.parent / "stow" / "hypr" / ".local" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_run(returncode: int = 0, stdout: str = "ok") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


def _option_response(value: int | float | str, type_name: str = "int") -> str:
    return json.dumps({type_name: value, "str": "", "float": 0.0, "custom_type": type_name})


# ---------------------------------------------------------------------------
# config module — the basis of get/set
# ---------------------------------------------------------------------------

def test_upsert_and_read_persisted(hypr_dir: Path) -> None:
    from hyprconf.config import upsert_option, read_persisted
    upsert_option("general", "gaps_in", "12")
    assert read_persisted("general", "gaps_in") == "12"


def test_save_pending_multi_section(hypr_dir: Path) -> None:
    from hyprconf.config import save_pending, read_all_persisted
    ok, count = save_pending({
        "general": {"gaps_in": "8", "border_size": "2"},
        "decoration.blur": {"enabled": "true"},
    })
    assert ok is True
    persisted = read_all_persisted()
    assert persisted["general:gaps_in"] == "8"
    assert persisted["decoration:blur:enabled"] == "true"


def test_overrides_file_contains_managed_marker(hypr_dir: Path) -> None:
    from hyprconf.config import upsert_option, OVERRIDES_FILE, MANAGED_MARKER
    upsert_option("general", "gaps_in", "5")
    assert MANAGED_MARKER in OVERRIDES_FILE.read_text()


def test_overrides_file_keys_sorted(hypr_dir: Path) -> None:
    from hyprconf.config import save_pending, OVERRIDES_FILE, MANAGED_MARKER
    save_pending({
        "z_section": {"z_key": "1"},
        "a_section": {"a_key": "2"},
    })
    text = OVERRIDES_FILE.read_text()
    managed_start = text.index(MANAGED_MARKER) + len(MANAGED_MARKER)
    managed_lines = [l for l in text[managed_start:].splitlines() if "=" in l]
    keys = [l.split("=")[0].strip() for l in managed_lines]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# schema module — validation used by set command
# ---------------------------------------------------------------------------

def test_validate_int_accepts_digits(hypr_dir: Path) -> None:
    from hyprconf.schema import validate_value
    ok, _ = validate_value("int", "42")
    assert ok


def test_validate_bool_rejects_garbage(hypr_dir: Path) -> None:
    from hyprconf.schema import validate_value
    ok, _ = validate_value("bool", "garbage")
    assert not ok


def test_validate_enum_must_match(hypr_dir: Path) -> None:
    from hyprconf.schema import validate_value
    ok, _ = validate_value("enum:dwindle,master", "dwindle")
    assert ok
    ok2, _ = validate_value("enum:dwindle,master", "other")
    assert not ok2


# ---------------------------------------------------------------------------
# hyprctl module — IPC wrapper (with mocked subprocess)
# ---------------------------------------------------------------------------

def test_is_active_returns_false_without_signature(
    hypr_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    from hyprconf import hyprctl
    assert hyprctl.is_active() is False


def test_is_active_returns_true_with_signature(
    hypr_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test-session")
    from hyprconf import hyprctl
    with patch("subprocess.run", return_value=_mock_run(0, "ok")):
        # is_active just checks the env var, no subprocess needed
        assert hyprctl.is_active() is True


def test_get_option_returns_string_value(
    hypr_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    from hyprconf import hyprctl
    # hyprctl.get_option returns the best human-readable field as a str
    response = _option_response(8, "int")
    with patch("subprocess.run", return_value=_mock_run(0, response)):
        result = hyprctl.get_option("general", "gaps_in")
    assert result is not None
    assert result == "8"


def test_set_option_calls_hyprctl(
    hypr_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    from hyprconf import hyprctl
    with patch("subprocess.run", return_value=_mock_run(0, "ok")) as mock_run:
        result = hyprctl.set_option("general", "gaps_in", "12")
    assert mock_run.called


def test_get_option_returns_none_when_inactive(
    hypr_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    from hyprconf import hyprctl
    result = hyprctl.get_option("general", "gaps_in")
    assert result is None


# ---------------------------------------------------------------------------
# keybinds — write then verify file content
# ---------------------------------------------------------------------------

def test_add_keybind_produces_correct_format(hypr_dir: Path) -> None:
    from hyprconf.keybinds import add_keybind, KEYBINDS_FILE
    add_keybind("bind", "SUPER", "T", "exec", "kitty", file=KEYBINDS_FILE)
    text = KEYBINDS_FILE.read_text()
    assert "bind = SUPER, T, exec, kitty" in text


def test_add_then_delete_keybind(hypr_dir: Path) -> None:
    from hyprconf.keybinds import (
        add_keybind, delete_keybind,
        read_keybinds_with_location, KEYBINDS_FILE,
    )
    KEYBINDS_FILE.write_text("")
    add_keybind("bind", "SUPER", "T", "exec", "kitty", file=KEYBINDS_FILE)
    entries = read_keybinds_with_location(KEYBINDS_FILE)
    assert len(entries) == 1
    delete_keybind(entries[0].file_path, entries[0].line_idx)
    assert read_keybinds_with_location(KEYBINDS_FILE) == []


# ---------------------------------------------------------------------------
# monitors — write then verify
# ---------------------------------------------------------------------------

def test_upsert_monitor_writes_correct_line(hypr_dir: Path) -> None:
    from hyprconf.monitors import upsert_monitor, MONITORS_FILE
    upsert_monitor("HDMI-A-1", "3840x2160@120", "0x0", "1.5", file=MONITORS_FILE)
    text = MONITORS_FILE.read_text()
    assert "monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5" in text


def test_upsert_monitor_with_extras(hypr_dir: Path) -> None:
    from hyprconf.monitors import upsert_monitor, MONITORS_FILE
    upsert_monitor("HDMI-A-1", "preferred", "auto", "1",
                   "vrr, 1, bitdepth, 10", file=MONITORS_FILE)
    text = MONITORS_FILE.read_text()
    assert "vrr, 1, bitdepth, 10" in text
