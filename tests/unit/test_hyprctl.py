"""Tests for hyprconf.hyprctl — thin wrapper around hyprctl IPC."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

LIB_DIR = Path(__file__).parent.parent.parent / "stow" / "hypr" / ".local" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import hyprconf.hyprctl as _hctl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend a Hyprland session is running."""
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test-session")


def _mock_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend no Hyprland session is running."""
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)


def _fake_run(stdout: str = "", returncode: int = 0):
    """Return a mock subprocess.run result."""
    return mock.MagicMock(stdout=stdout, returncode=returncode)


# ---------------------------------------------------------------------------
# is_active
# ---------------------------------------------------------------------------


def test_is_active_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    assert _hctl.is_active() is True


def test_is_active_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    assert _hctl.is_active() is False


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


def test_run_returns_stdout_on_success() -> None:
    with mock.patch("subprocess.run", return_value=_fake_run("ok", 0)):
        assert _hctl._run(["echo", "ok"]) == "ok"


def test_run_returns_none_on_nonzero() -> None:
    with mock.patch("subprocess.run", return_value=_fake_run("err", 1)):
        assert _hctl._run(["false"]) is None


def test_run_returns_none_on_timeout() -> None:
    import subprocess

    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 3)):
        assert _hctl._run(["sleep", "99"]) is None


def test_run_returns_none_on_file_not_found() -> None:
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        assert _hctl._run(["nonexistent"]) is None


# ---------------------------------------------------------------------------
# get_option
# ---------------------------------------------------------------------------


def test_get_option_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    assert _hctl.get_option("general", "gaps_in") is None


def test_get_option_returns_str_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    payload = json.dumps({"str": "dwindle", "int": 0, "float": 0.0})
    with mock.patch.object(_hctl, "_run", return_value=payload):
        assert _hctl.get_option("general", "layout") == "dwindle"


def test_get_option_returns_col_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    payload = json.dumps({"str": "", "col": 4278190080, "int": 0, "float": 0.0})
    with mock.patch.object(_hctl, "_run", return_value=payload):
        result = _hctl.get_option("general", "col.active_border")
        assert result is not None
        assert result.startswith("0x")


def test_get_option_returns_float_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    payload = json.dumps({"str": "", "int": 1, "float": 1.5})
    with mock.patch.object(_hctl, "_run", return_value=payload):
        assert _hctl.get_option("decoration", "rounding") == "1.5"


def test_get_option_returns_int_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    payload = json.dumps({"str": "", "int": 5, "float": 5.0})
    with mock.patch.object(_hctl, "_run", return_value=payload):
        assert _hctl.get_option("general", "gaps_in") == "5"


def test_get_option_returns_none_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="not json"):
        assert _hctl.get_option("general", "gaps_in") is None


def test_get_option_returns_none_when_run_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value=None):
        assert _hctl.get_option("general", "gaps_in") is None


# ---------------------------------------------------------------------------
# set_option
# ---------------------------------------------------------------------------


def test_set_option_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    assert _hctl.set_option("general", "gaps_in", "5") is False


def test_set_option_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.set_option("general", "gaps_in", "5") is True
        m.assert_called_once_with(["hyprctl", "keyword", "general:gaps_in", "5"])


def test_set_option_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value=None):
        assert _hctl.set_option("general", "gaps_in", "5") is False


# ---------------------------------------------------------------------------
# get_monitors
# ---------------------------------------------------------------------------


def test_get_monitors_success() -> None:
    monitors = [{"name": "HDMI-A-1", "width": 3840}]
    with mock.patch.object(_hctl, "_run", return_value=json.dumps(monitors)):
        assert _hctl.get_monitors() == monitors


def test_get_monitors_returns_empty_on_failure() -> None:
    with mock.patch.object(_hctl, "_run", return_value=None):
        assert _hctl.get_monitors() == []


def test_get_monitors_returns_empty_on_bad_json() -> None:
    with mock.patch.object(_hctl, "_run", return_value="not json"):
        assert _hctl.get_monitors() == []


# ---------------------------------------------------------------------------
# set_monitor
# ---------------------------------------------------------------------------


def test_set_monitor_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    assert _hctl.set_monitor("HDMI-A-1,preferred,auto,1") is False


def test_set_monitor_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.set_monitor("HDMI-A-1,preferred,auto,1") is True
        m.assert_called_once_with(["hyprctl", "keyword", "monitor", "HDMI-A-1,preferred,auto,1"])


# ---------------------------------------------------------------------------
# reload
# ---------------------------------------------------------------------------


def test_reload_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    assert _hctl.reload() is False


def test_reload_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.reload() is True
        m.assert_called_once_with(["hyprctl", "reload"])


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def test_dispatch_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    assert _hctl.dispatch("exec", "kitty") is False


def test_dispatch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.dispatch("exec", "kitty") is True
        m.assert_called_once_with(["hyprctl", "dispatch", "exec", "kitty"])


def test_dispatch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value=None):
        assert _hctl.dispatch("exec", "kitty") is False


# ---------------------------------------------------------------------------
# get_option — key formatting (dotted section → colon key)
# ---------------------------------------------------------------------------


def test_get_option_converts_dots_to_colons(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    payload = json.dumps({"str": "", "int": 1, "float": 1.0})
    with mock.patch.object(_hctl, "_run", return_value=payload) as m:
        _hctl.get_option("decoration.blur", "enabled")
        m.assert_called_once_with(["hyprctl", "getoption", "decoration:blur:enabled", "-j"])
