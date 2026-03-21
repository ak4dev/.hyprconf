"""Tests for update_wvkbd() in switch_theme.py."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

THEME_SWITCHER = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".config" / "hypr"
    / "scripts" / "theme-switcher" / "switch_theme.py"
)

# Import the module directly from its file path.
import importlib.util

spec = importlib.util.spec_from_file_location("switch_theme", THEME_SWITCHER)
st = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(st)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DARK_THEME = {
    "background": "#1e1e2e",
    "foreground": "#cdd6f4",
    "accent":     "#89b4fa",
}

LIGHT_THEME = {
    "background": "#eff1f5",
    "foreground": "#4c4f69",
    "accent":     "#1e66f5",
}


# ---------------------------------------------------------------------------
# update_wvkbd — colors file written correctly
# ---------------------------------------------------------------------------

def test_update_wvkbd_writes_colors_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st.update_wvkbd(DARK_THEME)

    colors = (tmp_path / ".config" / "wvkbd" / "colors").read_text()
    assert 'bg="#1e1e2e"' in colors
    assert 'fg="#cdd6f4"' in colors
    assert 'accent="#89b4fa"' in colors


def test_update_wvkbd_creates_config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_dir = tmp_path / ".config" / "wvkbd"
    assert not config_dir.exists()
    st.update_wvkbd(DARK_THEME)
    assert config_dir.is_dir()


def test_update_wvkbd_light_theme(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st.update_wvkbd(LIGHT_THEME)

    colors = (tmp_path / ".config" / "wvkbd" / "colors").read_text()
    assert 'bg="#eff1f5"' in colors
    assert 'fg="#4c4f69"' in colors


def test_update_wvkbd_no_background_skips_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    st.update_wvkbd({})  # no background key — should return silently
    assert not (tmp_path / ".config" / "wvkbd" / "colors").exists()


# ---------------------------------------------------------------------------
# update_wvkbd — restarts wvkbd when running
# ---------------------------------------------------------------------------

def test_update_wvkbd_restarts_when_running(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    pgrep_result = MagicMock(returncode=0, stdout="12345\n")
    popen_mock = MagicMock()

    with patch("subprocess.run", return_value=pgrep_result) as mock_run, \
         patch("subprocess.Popen", return_value=popen_mock) as mock_popen, \
         patch("shutil.which", return_value="/usr/local/bin/wvkbd-launcher"):
        st.update_wvkbd(DARK_THEME)

    mock_run.assert_called_once_with(
        ["pgrep", "-x", "wvkbd-mobintl"],
        capture_output=True, text=True,
    )
    mock_popen.assert_called_once_with(["/usr/local/bin/wvkbd-launcher"])


def test_update_wvkbd_no_restart_when_not_running(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    pgrep_result = MagicMock(returncode=1, stdout="")

    with patch("subprocess.run", return_value=pgrep_result), \
         patch("subprocess.Popen") as mock_popen, \
         patch("shutil.which", return_value="/usr/local/bin/wvkbd-launcher"):
        st.update_wvkbd(DARK_THEME)

    mock_popen.assert_not_called()


def test_update_wvkbd_no_restart_when_launcher_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    pgrep_result = MagicMock(returncode=0, stdout="12345\n")

    with patch("subprocess.run", return_value=pgrep_result), \
         patch("subprocess.Popen") as mock_popen, \
         patch("shutil.which", return_value=None):
        st.update_wvkbd(DARK_THEME)

    mock_popen.assert_not_called()


def test_update_wvkbd_handles_write_error_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        st.update_wvkbd(DARK_THEME)  # must not raise

    captured = capsys.readouterr()
    assert "Warning" in captured.out


# ---------------------------------------------------------------------------
# apply_theme — calls update_wvkbd when wvkbd-mobintl is in PATH
# ---------------------------------------------------------------------------

def test_apply_theme_calls_update_wvkbd_when_wvkbd_present(monkeypatch):
    calls: list[str] = []

    def _noop_update(theme):
        calls.append("update_wvkbd")

    monkeypatch.setattr(st, "update_wvkbd", _noop_update)
    monkeypatch.setattr(st, "load_theme", lambda _: DARK_THEME)
    monkeypatch.setattr(st, "load_kitty_theme", lambda _: None)
    monkeypatch.setattr(st, "generate_kitty_theme", lambda _: "dummy")
    monkeypatch.setattr(st, "update_waybar", lambda _: None)
    monkeypatch.setattr(st, "update_hyprpaper", lambda _: None)
    monkeypatch.setattr(st, "update_hyprtoolkit", lambda _: None)
    monkeypatch.setattr(st, "update_dunst", lambda _: None)
    monkeypatch.setattr(st, "update_gtk", lambda _: None)
    monkeypatch.setattr(st, "update_kde_colors", lambda _: None)
    monkeypatch.setattr(st, "update_qt_platform_theme", lambda _: None)
    monkeypatch.setattr(st, "update_vscode", lambda _: None)
    monkeypatch.setattr(st, "update_firefox", lambda _: None)
    monkeypatch.setattr(st, "update_hyprland_borders", lambda _: None)
    monkeypatch.setattr(st, "update_hyprlock_colors", lambda _: None)
    monkeypatch.setattr(st, "reload_hyprland", lambda: None)
    monkeypatch.setattr(st, "write_state", lambda _: None)
    monkeypatch.setattr(st, "notify_theme_change", lambda *_: None)

    with patch("shutil.which", return_value="/usr/bin/wvkbd-mobintl"):
        st.apply_theme("dummy-theme", reload=False)

    assert "update_wvkbd" in calls


def test_apply_theme_skips_update_wvkbd_when_wvkbd_absent(monkeypatch):
    calls: list[str] = []

    def _noop_update(theme):
        calls.append("update_wvkbd")

    monkeypatch.setattr(st, "update_wvkbd", _noop_update)
    monkeypatch.setattr(st, "load_theme", lambda _: DARK_THEME)
    monkeypatch.setattr(st, "load_kitty_theme", lambda _: None)
    monkeypatch.setattr(st, "generate_kitty_theme", lambda _: "dummy")
    monkeypatch.setattr(st, "update_waybar", lambda _: None)
    monkeypatch.setattr(st, "update_hyprpaper", lambda _: None)
    monkeypatch.setattr(st, "update_hyprtoolkit", lambda _: None)
    monkeypatch.setattr(st, "update_dunst", lambda _: None)
    monkeypatch.setattr(st, "update_gtk", lambda _: None)
    monkeypatch.setattr(st, "update_kde_colors", lambda _: None)
    monkeypatch.setattr(st, "update_qt_platform_theme", lambda _: None)
    monkeypatch.setattr(st, "update_vscode", lambda _: None)
    monkeypatch.setattr(st, "update_firefox", lambda _: None)
    monkeypatch.setattr(st, "update_hyprland_borders", lambda _: None)
    monkeypatch.setattr(st, "update_hyprlock_colors", lambda _: None)
    monkeypatch.setattr(st, "reload_hyprland", lambda: None)
    monkeypatch.setattr(st, "write_state", lambda _: None)
    monkeypatch.setattr(st, "notify_theme_change", lambda *_: None)

    with patch("shutil.which", return_value=None):
        st.apply_theme("dummy-theme", reload=False)

    assert "update_wvkbd" not in calls


# ---------------------------------------------------------------------------
# schema — hardware section registered
# ---------------------------------------------------------------------------

def test_schema_has_hardware_section():
    import importlib, sys
    LIB_DIR = Path(__file__).parent.parent.parent / "stow" / "hypr" / ".local" / "lib"
    if str(LIB_DIR) not in sys.path:
        sys.path.insert(0, str(LIB_DIR))
    import hyprconf.schema as schema
    importlib.reload(schema)
    assert "hardware" in schema.SECTION_ORDER
    assert schema.SECTION_LABELS.get("hardware") == "Hardware"
    # "hardware" is a display-only daemon-control section — intentionally absent
    # from OPTION_SCHEMA (which holds persistent config options only).
    assert "hardware" not in schema.OPTION_SCHEMA
