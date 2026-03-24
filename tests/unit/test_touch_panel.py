"""
Unit tests for touch-panel: hamburger-menu expand/collapse and OSK toggle.

These tests import the touch-panel script as a module, mock GtkLayerShell
so no compositor connection is required, and exercise:

- _expand_box starts hidden and is guarded by no_show_all
- show_all() on the window does NOT reveal the expand menu (regression guard)
- _on_fab toggles expand/collapse correctly (two-tap idempotent cycle)
- _on_osk spawns wvkbd-toggle
- _on_launcher collapses the menu and spawns hyprlauncher
- _reload_colors updates CSS without changing expand state
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
TOUCH_PANEL_PATH = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "touch-panel"

# Ensure gi is importable and GTK3 is available before we start.
pytest.importorskip("gi", reason="python-gobject not installed")

import gi  # noqa: E402
from importlib.machinery import SourceFileLoader  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")

# touch-panel has no .py extension — use SourceFileLoader directly.
_loader = SourceFileLoader("touch_panel", str(TOUCH_PANEL_PATH))
_spec = importlib.util.spec_from_loader("touch_panel", _loader)
_tp_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_loader.exec_module(_tp_mod)
TouchPanel = _tp_mod.TouchPanel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def panel():
    """TouchPanel with layer-shell and CSS init mocked to avoid compositor."""
    with (
        patch.object(TouchPanel, "_setup_layer_shell"),
        patch.object(TouchPanel, "_apply_css"),
    ):
        p = TouchPanel()
    yield p
    p.destroy()


# ---------------------------------------------------------------------------
# Expand-box initial state
# ---------------------------------------------------------------------------

def test_expand_box_has_no_show_all(panel: TouchPanel) -> None:
    """no_show_all must be set so show_all() cannot un-hide the menu."""
    assert panel._expand_box.get_no_show_all() is True


def test_expand_box_hidden_on_init(panel: TouchPanel) -> None:
    """Expand box is not visible before any FAB tap."""
    assert panel._expand_box.get_visible() is False


def test_show_all_does_not_reveal_expand_box(panel: TouchPanel) -> None:
    """show_all() — called by main() — must not make the expand box visible."""
    panel.show_all()
    assert panel._expand_box.get_visible() is False


def test_initial_expanded_flag_is_false(panel: TouchPanel) -> None:
    assert panel._expanded is False


# ---------------------------------------------------------------------------
# FAB toggle
# ---------------------------------------------------------------------------

def test_fab_first_tap_expands(panel: TouchPanel) -> None:
    panel._on_fab(panel._btn_fab)
    assert panel._expanded is True
    assert panel._expand_box.get_visible() is True


def test_fab_second_tap_collapses(panel: TouchPanel) -> None:
    panel._on_fab(panel._btn_fab)
    panel._on_fab(panel._btn_fab)
    assert panel._expanded is False
    assert panel._expand_box.get_visible() is False


def test_fab_three_taps_ends_expanded(panel: TouchPanel) -> None:
    for _ in range(3):
        panel._on_fab(panel._btn_fab)
    assert panel._expanded is True
    assert panel._expand_box.get_visible() is True


def test_fab_expand_makes_child_buttons_visible(panel: TouchPanel) -> None:
    """After expand, both the launcher and OSK buttons must be visible."""
    panel._on_fab(panel._btn_fab)
    assert panel._btn_launcher.get_visible() is True
    assert panel._btn_osk.get_visible() is True


# ---------------------------------------------------------------------------
# OSK button
# ---------------------------------------------------------------------------

def test_on_osk_spawns_wvkbd_toggle(
    panel: TouchPanel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tapping the OSK button spawns wvkbd-toggle."""
    toggle_path = tmp_path / ".local" / "bin" / "wvkbd-toggle"
    toggle_path.parent.mkdir(parents=True)
    toggle_path.touch()
    toggle_path.chmod(0o755)

    monkeypatch.setenv("HOME", str(tmp_path))
    with patch.object(_tp_mod.subprocess, "Popen") as mock_popen:
        panel._on_osk(panel._btn_osk)

    mock_popen.assert_called_once_with([str(toggle_path)])


def test_on_osk_silent_when_toggle_missing(
    panel: TouchPanel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No exception if wvkbd-toggle does not exist."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch.object(_tp_mod.subprocess, "Popen") as mock_popen:
        panel._on_osk(panel._btn_osk)  # toggle file absent

    mock_popen.assert_not_called()


# ---------------------------------------------------------------------------
# Launcher button
# ---------------------------------------------------------------------------

def test_on_launcher_spawns_hyprlauncher(panel: TouchPanel) -> None:
    with patch.object(_tp_mod.subprocess, "Popen") as mock_popen:
        panel._on_launcher(panel._btn_launcher)

    mock_popen.assert_called_once_with(["hyprlauncher"])


def test_on_launcher_collapses_menu(panel: TouchPanel) -> None:
    """After launcher tap the menu must be collapsed regardless of prior state."""
    panel._on_fab(panel._btn_fab)  # expand first
    assert panel._expanded is True

    with patch.object(_tp_mod.subprocess, "Popen"):
        panel._on_launcher(panel._btn_launcher)

    assert panel._expanded is False
    assert panel._expand_box.get_visible() is False


# ---------------------------------------------------------------------------
# Color reload
# ---------------------------------------------------------------------------

def test_reload_colors_preserves_collapsed_state(panel: TouchPanel, tmp_path: Path) -> None:
    """SIGUSR1 color reload must not change the panel's expand state."""
    with patch.object(TouchPanel, "_apply_css"):
        panel._reload_colors()

    assert panel._expanded is False
    assert panel._expand_box.get_visible() is False


def test_reload_colors_preserves_expanded_state(panel: TouchPanel) -> None:
    """Color reload while expanded must leave the menu expanded."""
    panel._on_fab(panel._btn_fab)  # expand

    with patch.object(TouchPanel, "_apply_css"):
        panel._reload_colors()

    assert panel._expanded is True
    assert panel._expand_box.get_visible() is True
