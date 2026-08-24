"""Tests for hyprconf.hyprctl — thin wrapper around hyprctl IPC."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

LIB_DIR = Path(__file__).parent.parent.parent / "lib"
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


def test_get_option_returns_custom_field(monkeypatch: pytest.MonkeyPatch) -> None:
    # CUSTOM-type options (e.g. multi-value gaps) report only `custom`; gaps_in
    # always comes through here, so it must be read or `get` shows the default.
    _mock_active(monkeypatch)
    payload = json.dumps({"custom": "3 3 3 3", "set": True})
    with mock.patch.object(_hctl, "_run", return_value=payload):
        assert _hctl.get_option("general", "gaps_in") == "3 3 3 3"


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
    """Live changes go through `hyprctl eval 'hl.config({ … })'` — on the
    0.56 Lua parser the keyword subcommand is a silent no-op that exits 0."""
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.set_option("general", "gaps_in", "5") is True
        m.assert_called_once_with(["hyprctl", "eval", "hl.config({ general = { gaps_in = 5 } })"])


def test_set_option_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value=None):
        assert _hctl.set_option("general", "gaps_in", "5") is False


def test_set_option_error_reply_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    err = "error: [string]:1: unknown config key 'general.no_such_option_xyz'"
    with mock.patch.object(_hctl, "_run", return_value=err):
        assert _hctl.set_option("general", "no_such_option_xyz", "5") is False


def test_config_call_nests_dotted_sections_and_types_bools() -> None:
    assert (
        _hctl.config_call("decoration.blur", "enabled", "true")
        == "hl.config({ decoration = { blur = { enabled = true } } })"
    )
    assert (
        _hctl.config_call("decoration.blur", "enabled", "0")
        == "hl.config({ decoration = { blur = { enabled = false } } })"
    )


def test_config_call_quotes_strings_and_keeps_numbers_bare() -> None:
    assert _hctl.config_call("general", "layout", "master") == (
        'hl.config({ general = { layout = "master" } })'
    )
    assert _hctl.config_call("input", "sensitivity", "0.5") == (
        "hl.config({ input = { sensitivity = 0.5 } })"
    )
    # Colours/gradients are strings to the Lua API (HL.ConfigValueTypes), and
    # a dotted key nests like a section: `col.active_border` is
    # `col = { active_border = … }` (Omarchy's default/hypr/looknfeel.lua).
    assert _hctl.config_call("general", "col.active_border", "0xffffffff 45deg") == (
        'hl.config({ general = { col = { active_border = "0xffffffff 45deg" } } })'
    )


# ---------------------------------------------------------------------------
# eval_lua
# ---------------------------------------------------------------------------


def test_eval_lua_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    with mock.patch.object(_hctl, "_run") as m:
        assert _hctl.eval_lua("hl.config({})") is False
        m.assert_not_called()


def test_eval_lua_passes_the_chunk_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.eval_lua("hl.config({ general = { gaps_in = 3 } })") is True
        m.assert_called_once_with(["hyprctl", "eval", "hl.config({ general = { gaps_in = 3 } })"])


def test_eval_lua_nonzero_exit_or_error_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value=None):
        assert _hctl.eval_lua("garbage(") is False
    with mock.patch.object(_hctl, "_run", return_value="error: syntax error near ')'"):
        assert _hctl.eval_lua("garbage(") is False


# ---------------------------------------------------------------------------
# apply_monitor / disable_monitor — hl.monitor({ … }) via eval
# ---------------------------------------------------------------------------


def test_apply_monitor_evals_hl_monitor_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.apply_monitor("DP-1", "1920x1080@60", "0x0", "1.0", "vrr, 1") is True
        m.assert_called_once_with(
            [
                "hyprctl",
                "eval",
                'hl.monitor({ output = "DP-1", mode = "1920x1080@60", position = "0x0", '
                "scale = 1.0, vrr = 1 })",
            ]
        )


def test_apply_monitor_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_inactive(monkeypatch)
    with mock.patch.object(_hctl, "_run") as m:
        assert _hctl.apply_monitor("DP-1", "preferred", "auto", "1") is False
        m.assert_not_called()


def test_disable_monitor_evals_disabled_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_active(monkeypatch)
    with mock.patch.object(_hctl, "_run", return_value="ok") as m:
        assert _hctl.disable_monitor("eDP-1") is True
        m.assert_called_once_with(
            ["hyprctl", "eval", 'hl.monitor({ output = "eDP-1", disabled = true })']
        )


def test_nothing_shipped_calls_hyprctl_keyword() -> None:
    """The keyword subcommand is a silent no-op on Hyprland 0.56's Lua parser
    ("keyword can't work with non-legacy parsers. Use eval.", exit 0), so no
    shipped code may build such an argv."""
    root = Path(__file__).resolve().parents[2]
    shipped = [*(root / "lib" / "hyprconf").glob("*.py"), root / "tui" / "main.py"]
    for f in shipped:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            assert not ('"hyprctl"' in line and '"keyword"' in line), (
                f"{f.relative_to(root)}:{n} builds a hyprctl keyword call"
            )


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
