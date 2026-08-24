"""Gap coverage tests for hyprconf.hyprctl — IPC wrapper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

LIB_DIR = Path(__file__).parent.parent.parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import hyprconf.hyprctl as hyprctl


def _mock_run(returncode: int = 0, stdout: str = "ok") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


def _option_json(**fields) -> str:
    base = {"str": "", "int": 0, "float": 0.0, "col": 0, "custom_type": "int"}
    base.update(fields)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# _run — exception paths
# ---------------------------------------------------------------------------


def test_run_returns_none_on_timeout(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="hyprctl", timeout=3)):
        result = hyprctl._run(["hyprctl", "version"])
    assert result is None


def test_run_returns_none_on_file_not_found(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", side_effect=FileNotFoundError("hyprctl not found")):
        result = hyprctl._run(["hyprctl", "version"])
    assert result is None


def test_run_returns_none_on_oserror(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", side_effect=OSError("permission denied")):
        result = hyprctl._run(["hyprctl", "version"])
    assert result is None


def test_run_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="error")):
        result = hyprctl._run(["hyprctl", "something"])
    assert result is None


# ---------------------------------------------------------------------------
# get_option — value type paths
# ---------------------------------------------------------------------------


def test_get_option_returns_str_field(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    payload = _option_json(str="some-string-value", int=0, float=0.0)
    with patch("subprocess.run", return_value=_mock_run(0, payload)):
        result = hyprctl.get_option("input", "kb_layout")
    assert result == "some-string-value"


def test_get_option_returns_color_as_hex(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    # col = 0xff00ff00 (green)
    payload = _option_json(col=0xFF00FF00, str="", int=0, float=0.0)
    with patch("subprocess.run", return_value=_mock_run(0, payload)):
        result = hyprctl.get_option("general", "col.active_border")
    assert result is not None
    assert result.startswith("0x")
    assert "ff00ff00" in result


def test_get_option_returns_float_with_fraction(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    payload = _option_json(float=1.5, int=1, str="", col=0)
    with patch("subprocess.run", return_value=_mock_run(0, payload)):
        result = hyprctl.get_option("general", "sensitivity")
    assert result == "1.5"


def test_get_option_falls_back_to_int(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    payload = _option_json(int=8, float=0.0, str="", col=0)
    with patch("subprocess.run", return_value=_mock_run(0, payload)):
        result = hyprctl.get_option("general", "gaps_in")
    assert result == "8"


def test_get_option_returns_none_on_json_error(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(0, "not-json{")):
        result = hyprctl.get_option("general", "gaps_in")
    assert result is None


def test_get_option_returns_none_when_run_fails(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(returncode=1, stdout="")):
        result = hyprctl.get_option("general", "gaps_in")
    assert result is None


# ---------------------------------------------------------------------------
# set_option
# ---------------------------------------------------------------------------


def test_set_option_returns_false_when_inactive(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert hyprctl.set_option("general", "gaps_in", "5") is False


def test_set_option_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(0, "ok")) as run:
        assert hyprctl.set_option("general", "gaps_in", "5") is True
    argv = run.call_args.args[0]
    assert argv[:2] == ["hyprctl", "eval"]
    assert argv[2] == "hl.config({ general = { gaps_in = 5 } })"


def test_set_option_treats_error_reply_as_failure(monkeypatch):
    """hyprctl eval reports a bad key as `error: …` (exit 7 on the real
    binary); a 0 exit with an error reply must not read as success either."""
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    err = "error: [string]:1: unknown config key 'general.no_such_option_xyz'"
    with patch("subprocess.run", return_value=_mock_run(0, err)):
        assert hyprctl.set_option("general", "no_such_option_xyz", "5") is False
    with patch("subprocess.run", return_value=_mock_run(7, "")):
        assert hyprctl.set_option("general", "no_such_option_xyz", "5") is False


# ---------------------------------------------------------------------------
# get_monitors
# ---------------------------------------------------------------------------


def test_get_monitors_returns_empty_when_no_hyprland(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    # _run returns None when hyprctl not found (FileNotFoundError)
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = hyprctl.get_monitors()
    assert result == []


def test_get_monitors_returns_empty_on_json_error(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(0, "bad json{")):
        result = hyprctl.get_monitors()
    assert result == []


def test_get_monitors_returns_parsed_list(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    monitors = [{"name": "eDP-1", "width": 1920, "height": 1080}]
    with patch("subprocess.run", return_value=_mock_run(0, json.dumps(monitors))):
        result = hyprctl.get_monitors()
    assert result == monitors


# ---------------------------------------------------------------------------
# reload
# ---------------------------------------------------------------------------


def test_reload_returns_false_when_inactive(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert hyprctl.reload() is False


def test_reload_returns_true_when_active(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(0, "ok")):
        assert hyprctl.reload() is True


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def test_dispatch_returns_false_when_inactive(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert hyprctl.dispatch("exec", "kitty") is False


def test_dispatch_returns_true_when_active(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    with patch("subprocess.run", return_value=_mock_run(0, "ok")):
        assert hyprctl.dispatch("exec", "kitty") is True
