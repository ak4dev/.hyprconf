"""Tests for new theme-switcher behaviours added in this session:
  - _kill_process_if_running() helper
  - hyperlauncher restart after update_hyprtoolkit()
  - Dolphin ColorScheme write in update_kde_colors()
  - Firefox running-state guard in update_firefox()
  - update_touch_panel() (see also test_hardware_features.py)
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

THEME_SWITCHER = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".config" / "hypr"
    / "scripts" / "theme-switcher" / "switch_theme.py"
)

import importlib.util

spec = importlib.util.spec_from_file_location("switch_theme", THEME_SWITCHER)
st = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(st)  # type: ignore[union-attr]

DARK_THEME = {
    "background": "#1e1e2e",
    "foreground": "#cdd6f4",
    "accent":     "#89b4fa",
}


# ---------------------------------------------------------------------------
# _kill_process_if_running()
# ---------------------------------------------------------------------------

def test_kill_process_sends_sigterm(monkeypatch):
    kill_calls: list = []

    def fake_run(cmd, **_kw):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "1234\n5678\n"
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    result = st._kill_process_if_running("fakeprog")
    assert result is True
    assert (1234, signal.SIGTERM) in kill_calls
    assert (5678, signal.SIGTERM) in kill_calls


def test_kill_process_returns_false_when_not_running(monkeypatch):
    def fake_run(cmd, **_kw):
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    kill_calls: list = []
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    result = st._kill_process_if_running("notrunning")
    assert result is False
    assert kill_calls == []


def test_kill_process_ignores_stale_pids(monkeypatch):
    """ProcessLookupError (stale PID) must not raise."""
    def fake_run(cmd, **_kw):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "9999\n"
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    # Must not raise
    st._kill_process_if_running("ghost")


# ---------------------------------------------------------------------------
# update_hyprtoolkit() — kills hyperlauncher if running
# ---------------------------------------------------------------------------

def test_update_hyprtoolkit_kills_hyperlauncher(tmp_path, monkeypatch):
    """After writing hyprtoolkit.conf, hyperlauncher should be sent SIGTERM."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(st.os, "makedirs", lambda *a, **kw: None)
    monkeypatch.setattr(st, "HYPRTOOLKIT_CONF_FILE", str(tmp_path / "hyprtoolkit.conf"))

    killed: list = []

    def fake_kill_process(name: str) -> bool:
        killed.append(name)
        return True

    monkeypatch.setattr(st, "_kill_process_if_running", fake_kill_process)

    # patch open so we don't need actual filesystem
    with patch("builtins.open", unittest_mock_open()):
        st.update_hyprtoolkit(DARK_THEME)

    assert "hyprlauncher" in killed


def test_update_hyprtoolkit_does_not_raise_when_hyprlauncher_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(st.os, "makedirs", lambda *a, **kw: None)
    monkeypatch.setattr(st, "HYPRTOOLKIT_CONF_FILE", str(tmp_path / "hyprtoolkit.conf"))

    def fake_kill_process(name: str) -> bool:
        return False  # process not running

    monkeypatch.setattr(st, "_kill_process_if_running", fake_kill_process)

    with patch("builtins.open", unittest_mock_open()):
        st.update_hyprtoolkit(DARK_THEME)  # must not raise


# ---------------------------------------------------------------------------
# update_kde_colors() — writes ColorScheme to dolphinrc
# ---------------------------------------------------------------------------

def test_update_kde_colors_writes_dolphin_colorscheme(monkeypatch, tmp_path):
    """kwriteconfig6 should be called to write ColorScheme=SwitchThemeGenerated."""
    kwrite_calls: list = []

    def fake_which(name: str):
        return "/usr/bin/kwriteconfig6" if name == "kwriteconfig6" else None

    def fake_run(cmd, **_kw):
        kwrite_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.shutil, "which", fake_which)
    monkeypatch.setattr(st.subprocess, "run", fake_run)

    # Patch file writes so we don't touch the real filesystem
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    st.update_kde_colors(DARK_THEME)

    dolphin_calls = [c for c in kwrite_calls if "dolphinrc" in c]
    assert len(dolphin_calls) == 1
    cmd = dolphin_calls[0]
    assert "SwitchThemeGenerated" in cmd
    assert "--key" in cmd
    assert "ColorScheme" in cmd


def test_update_kde_colors_falls_back_to_kwriteconfig5(monkeypatch, tmp_path):
    """If kwriteconfig6 is absent, kwriteconfig5 should be tried."""
    kwrite_calls: list = []

    def fake_which(name: str):
        if name == "kwriteconfig5":
            return "/usr/bin/kwriteconfig5"
        return None  # kwriteconfig6 absent

    def fake_run(cmd, **_kw):
        kwrite_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.shutil, "which", fake_which)
    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    st.update_kde_colors(DARK_THEME)

    dolphin_calls = [c for c in kwrite_calls if "dolphinrc" in c]
    assert len(dolphin_calls) == 1
    assert dolphin_calls[0][0] in ("kwriteconfig5", "/usr/bin/kwriteconfig5")


def test_update_kde_colors_skips_dolphin_when_kwriteconfig_absent(monkeypatch, tmp_path):
    """No dolphin write if neither kwriteconfig6 nor kwriteconfig5 is present."""
    subprocess_calls: list = []

    def fake_which(name: str):
        if name in ("kwriteconfig6", "kwriteconfig5"):
            return None
        return f"/usr/bin/{name}"  # other tools present

    def fake_run(cmd, **_kw):
        subprocess_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.shutil, "which", fake_which)
    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    st.update_kde_colors(DARK_THEME)

    dolphin_calls = [c for c in subprocess_calls if any("dolphinrc" in str(a) for a in c)]
    assert dolphin_calls == []


# ---------------------------------------------------------------------------
# update_firefox() — running-state guard
# ---------------------------------------------------------------------------

def test_firefox_skips_extensions_json_when_running(tmp_path, monkeypatch):
    """When Firefox is running, set_firefox_theme_activation must not be called."""
    activation_calls: list = []

    monkeypatch.setattr(st, "_is_process_running", lambda name: True)  # Firefox is running
    monkeypatch.setattr(st.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0))
    monkeypatch.setattr(st, "get_default_firefox_profile", lambda: tmp_path)
    monkeypatch.setattr(st, "parse_user_js", lambda *_: {})
    monkeypatch.setattr(st, "ensure_firefox_theme_payload", lambda *_: None)
    monkeypatch.setattr(st, "set_firefox_theme_activation",
                        lambda p, tid: activation_calls.append(tid) or True)
    monkeypatch.setattr(st, "write_firefox_userchrome", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userjs", lambda *_: None)

    st.update_firefox(DARK_THEME)

    assert activation_calls == [], "extensions.json must not be written while Firefox is running"


def test_firefox_updates_extensions_json_when_not_running(tmp_path, monkeypatch):
    """When Firefox is not running, theme activation should proceed normally."""
    activation_calls: list = []

    monkeypatch.setattr(st, "_is_process_running", lambda name: False)  # Firefox NOT running
    monkeypatch.setattr(st, "get_default_firefox_profile", lambda: tmp_path)
    monkeypatch.setattr(st, "parse_user_js", lambda *_: {})
    monkeypatch.setattr(st, "ensure_firefox_theme_payload", lambda *_: None)
    monkeypatch.setattr(st, "resolve_firefox_theme_id", lambda *_: None)
    monkeypatch.setattr(st, "get_firefox_builtin_theme_id", lambda _: "firefox-compact-dark@mozilla.org")
    monkeypatch.setattr(st, "set_firefox_theme_activation",
                        lambda p, tid: activation_calls.append(tid) or True)
    monkeypatch.setattr(st, "write_firefox_userchrome", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userjs", lambda *_: None)

    st.update_firefox(DARK_THEME)

    assert len(activation_calls) == 1
    assert "compact-dark" in activation_calls[0]


def test_firefox_sends_notify_when_running(tmp_path, monkeypatch, capsys):
    """notify-send should be called when Firefox is running."""
    notify_calls: list = []

    monkeypatch.setattr(st, "_is_process_running", lambda name: True)  # Firefox is running

    def fake_run(cmd, **_kw):
        m = MagicMock()
        if cmd[0] == "notify-send":
            notify_calls.append(cmd)
        m.returncode = 0
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st, "get_default_firefox_profile", lambda: tmp_path)
    monkeypatch.setattr(st, "parse_user_js", lambda *_: {})
    monkeypatch.setattr(st, "ensure_firefox_theme_payload", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userchrome", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userjs", lambda *_: None)

    st.update_firefox(DARK_THEME)

    assert notify_calls, "notify-send should have been called"
    assert any("restart" in " ".join(c).lower() for c in notify_calls)


# ---------------------------------------------------------------------------
# Helper: unittest mock_open compatible with write_text
# ---------------------------------------------------------------------------

def unittest_mock_open():
    """Return a mock open() that accepts positional and keyword args."""
    from unittest.mock import mock_open
    m = mock_open()
    m.return_value.__enter__ = lambda s: s
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m
