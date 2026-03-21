"""
TUI smoke tests using Textual's built-in App.run_test() + Pilot framework.

These tests exercise the TUI in fully headless mode — no terminal, no
Hyprland session, and no display required.  They are safe to run in CI.

Design principles:
- Each test is narrow: it verifies ONE behaviour.
- Pilot actions are kept minimal — we test state, not keypress sequences.
- Heavy monkeypatching keeps external deps (hyprctl, file I/O) isolated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — TUI lives outside the lib tree
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
LIB_DIR   = REPO_ROOT / "stow" / "hypr" / ".local" / "lib"
TUI_DIR   = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "hyprconf-tui"

for p in (str(LIB_DIR), str(TUI_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Textual is required for TUI tests — skip gracefully if absent
pytest.importorskip("textual", reason="python-textual not installed")

from textual.pilot import Pilot  # noqa: E402 — after importorskip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def patched_tui_env(hypr_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Patch all external calls the TUI makes on startup."""
    # Hyprland not active → TUI falls back to file-only mode gracefully
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)

    # Patch hyprctl.is_active used by TUI
    monkeypatch.setattr("hyprconf.hyprctl.is_active", lambda: False)

    # Patch get_monitors so MonitorEditScreen can open without IPC
    monkeypatch.setattr(
        "hyprconf.hyprctl.get_monitors",
        lambda: [{"name": "HDMI-A-1", "description": "Test Monitor"}],
    )

    # Seed a minimal current-theme file so the TUI doesn't error on startup
    theme_file = hypr_dir / ".current-theme"
    theme_file.write_text(json.dumps({
        "name": "test-theme",
        "background": "#1d2021",
        "foreground": "#ebdbb2",
        "accent": "#fabd2f",
        "comment": "#928374",
    }))

    return hypr_dir


# ---------------------------------------------------------------------------
# Import the app (deferred so importorskip has a chance to run)
# ---------------------------------------------------------------------------

def _get_app_class():
    try:
        import main as tui_main
        return tui_main.HyprconfApp
    except ImportError:
        pytest.skip("TUI main.py not importable — check sys.path")


# ---------------------------------------------------------------------------
# Smoke test: app starts without crashing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_starts(patched_tui_env: Path) -> None:
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # The brand bar should be present
        brand = app.query_one("#brand-bar")
        assert brand is not None


# ---------------------------------------------------------------------------
# Smoke test: sidebar is populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sidebar_has_items(patched_tui_env: Path) -> None:
    from textual.widgets import ListView
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        sidebar = app.query_one("#section-list", ListView)
        assert len(sidebar) > 0


# ---------------------------------------------------------------------------
# Smoke test: option table loads when a section is selected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_section_loads_options(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Press down in the sidebar and Enter to select a section
        await pilot.press("tab")   # focus sidebar
        await pilot.press("enter") # select first item
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert table.row_count > 0


# ---------------------------------------------------------------------------
# OptionSelectScreen: opens and cancels cleanly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_option_select_screen_cancel(patched_tui_env: Path) -> None:
    import main as tui_main
    HyprconfApp = _get_app_class()
    OptionSelectScreen = tui_main.OptionSelectScreen

    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(
            OptionSelectScreen(title="Pick a value",
                               options=[("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma")],
                               current="beta"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        # Escape should dismiss without a value
        await pilot.press("escape")
        await pilot.pause()
        assert received == [None]


# ---------------------------------------------------------------------------
# OptionSelectScreen: select an item with Enter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_option_select_screen_select(patched_tui_env: Path) -> None:
    import main as tui_main
    HyprconfApp = _get_app_class()
    OptionSelectScreen = tui_main.OptionSelectScreen

    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(
            OptionSelectScreen(title="Pick a value",
                               options=[("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma")],
                               current="alpha"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        # "alpha" is already focused (current); press Enter
        await pilot.press("enter")
        await pilot.pause()
        assert received == ["alpha"]


# ---------------------------------------------------------------------------
# SliderBar: value clamps to min/max
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slider_bar_clamps_at_max(patched_tui_env: Path) -> None:
    import main as tui_main
    HyprconfApp = _get_app_class()
    SliderBar = tui_main.SliderBar

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        slider = SliderBar(min_val=0, max_val=1.0, value=0.9, step=0.1, fine_step=0.01, is_int=False)
        await app.mount(slider)
        await pilot.pause()
        # Move up past max
        slider.action_step(+1)
        slider.action_step(+1)
        slider.action_step(+1)
        assert slider.value <= 1.0


@pytest.mark.asyncio
async def test_slider_bar_clamps_at_min(patched_tui_env: Path) -> None:
    import main as tui_main
    HyprconfApp = _get_app_class()
    SliderBar = tui_main.SliderBar

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        slider = SliderBar(min_val=0, max_val=10, value=1, step=1, fine_step=1, is_int=True)
        await app.mount(slider)
        await pilot.pause()
        slider.action_step(-5)
        assert slider.value >= 0


@pytest.mark.asyncio
async def test_slider_bar_home_end(patched_tui_env: Path) -> None:
    import main as tui_main
    HyprconfApp = _get_app_class()
    SliderBar = tui_main.SliderBar

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        slider = SliderBar(min_val=0, max_val=100, value=50, step=5, fine_step=1, is_int=True)
        await app.mount(slider)
        await pilot.pause()
        slider.action_to_min()
        assert slider.value == 0
        slider.action_to_max()
        assert slider.value == 100



# ---------------------------------------------------------------------------
# Hardware section: loads without error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hardware_section_loads(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable
    from unittest.mock import patch as _patch
    import subprocess as _sp

    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    # Patch sysfs and pgrep calls so the test is hermetic
    with _patch("glob.iglob", return_value=iter([])), \
         _patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")) :
        async with app.run_test(size=(120, 40)) as pilot:
            import main as tui_main
            app._load_section("hardware")
            await pilot.pause()
            table = app.query_one("#option-table", DataTable)
            assert table.row_count >= 4  # detection rows + daemon rows
