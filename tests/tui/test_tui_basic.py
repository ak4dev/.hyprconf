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


# ---------------------------------------------------------------------------
# Auto-save on exit (on_unmount fires regardless of exit mechanism: q or Ctrl+C)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pending_changes_saved_on_quit(patched_tui_env: Path) -> None:
    """Pending TUI changes must be written to disk when the user quits with q."""
    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    saved: list[dict] = []

    def _fake_save(pending):
        saved.append(dict(pending))
        return True, sum(len(v) for v in pending.values())

    # Patch OUTSIDE run_test so it's active during on_unmount (fires in run_test cleanup)
    with patch("main.save_pending", side_effect=_fake_save):
        async with app.run_test(size=(120, 40)) as pilot:
            app._pending = {"general": {"border_size": "3"}}
            await pilot.press("q")

    assert saved, "on_unmount must call save_pending when there are pending changes"
    assert saved[0].get("general", {}).get("border_size") == "3"


@pytest.mark.asyncio
async def test_no_save_called_on_quit_when_nothing_pending(patched_tui_env: Path) -> None:
    """on_unmount must not call save_pending when there are no pending changes."""
    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    saved: list[dict] = []

    def _fake_save(pending):
        saved.append(dict(pending))
        return True, 0

    with patch("main.save_pending", side_effect=_fake_save):
        async with app.run_test(size=(120, 40)) as pilot:
            app._pending = {}
            await pilot.press("q")

    assert not saved, "on_unmount must not call save_pending when nothing is pending"


@pytest.mark.asyncio
async def test_pending_changes_saved_on_ctrlc(patched_tui_env: Path) -> None:
    """Pending TUI changes must be written to disk on Ctrl+C (on_unmount path)."""
    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    saved: list[dict] = []

    def _fake_save(pending):
        saved.append(dict(pending))
        return True, sum(len(v) for v in pending.values())

    with patch("main.save_pending", side_effect=_fake_save):
        async with app.run_test(size=(120, 40)) as pilot:
            app._pending = {"decoration": {"rounding": "8"}}
            # Simulate Ctrl+C exit path (app.exit() directly, not via action_quit)
            app.exit()

    assert saved, "on_unmount must call save_pending even when app.exit() is called directly"
    assert saved[0].get("decoration", {}).get("rounding") == "8"


@pytest.mark.asyncio
async def test_action_refresh_reloads_section(patched_tui_env: Path) -> None:
    """Pressing r must reload the current section without error."""
    from textual.widgets import DataTable
    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("r")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert table.row_count > 0



@pytest.mark.asyncio
async def test_on_unmount_logs_stderr_on_save_failure(
    patched_tui_env: Path, capsys
) -> None:
    """on_unmount must print a warning to stderr when save_pending returns False."""
    import sys
    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    stderr_msgs: list[str] = []
    real_print = print

    def _capture_print(*args, file=None, **kwargs):
        if file is sys.stderr:
            stderr_msgs.append(" ".join(str(a) for a in args))
        else:
            real_print(*args, file=file, **kwargs)

    def _failing_save(pending):
        return False, 0

    with patch("main.save_pending", side_effect=_failing_save), \
         patch("builtins.print", side_effect=_capture_print):
        async with app.run_test(size=(120, 40)) as pilot:
            app._pending = {"general": {"border_size": "5"}}
            await pilot.press("q")

    assert any("auto-save" in msg.lower() or "WARNING" in msg for msg in stderr_msgs), \
        "on_unmount must print a warning to stderr when save_pending fails"


# ---------------------------------------------------------------------------
# Regression: block-field editing — line with no '=' must not crash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blkfld_no_equals_line_yields_empty_current_val(
    patched_tui_env: Path,
) -> None:
    """Regression: editing a block field whose config line has no '=' must
    yield an empty current value, not raise an IndexError."""
    # Reproduce the logic that was previously `split("=", 1)[1]`
    # This test verifies the guard is in place in the TUI source.
    import main as tui_main, inspect

    src = inspect.getsource(tui_main.HyprconfApp.on_row_selected)
    # Old (buggy) pattern: split("=", 1)[1].strip()
    assert 'split("=", 1)[1]' not in src, (
        "TUI still uses unguarded split()[1] — IndexError regression"
    )
    # New pattern must check len before indexing
    assert 'len(_parts) > 1' in src, (
        "TUI must guard split result with len() check before indexing"
    )


# ---------------------------------------------------------------------------
# Regression: _set_wallpaper must use hyprpaper IPC, not hyprctl keyword
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_wallpaper_uses_hyprpaper_ipc(
    patched_tui_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: _set_wallpaper must call `hyprctl hyprpaper wallpaper`
    (hyprpaper's own IPC), NOT `hyprctl keyword hyprpaper:wallpaper`."""
    import main as tui_main

    run_calls: list[list[str]] = []
    monkeypatch.setattr(tui_main, "_run", lambda args, **kw: (run_calls.append(list(args)), "ok")[1])

    fake_wp = tmp_path / "bg.png"
    fake_wp.write_bytes(b"")

    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        app._set_wallpaper(fake_wp)
        await pilot.pause()

    # Must call hyprctl hyprpaper wallpaper …
    assert any(
        len(a) >= 3 and a[:3] == ["hyprctl", "hyprpaper", "wallpaper"]
        for a in run_calls
    ), "Expected `hyprctl hyprpaper wallpaper` call — hyprpaper has its own IPC"
    # Must NOT call hyprctl keyword … hyprpaper …
    assert not any(
        len(a) >= 2 and a[0] == "hyprctl" and a[1] == "keyword"
        and any("hyprpaper" in str(x) for x in a)
        for a in run_calls
    ), "`hyprctl keyword hyprpaper` is wrong — hyprpaper is not a Hyprland option section"
