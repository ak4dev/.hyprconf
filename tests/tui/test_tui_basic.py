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
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — TUI lives outside the lib tree
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
LIB_DIR = REPO_ROOT / "stow" / "hypr" / ".local" / "lib"
TUI_DIR = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "hyprconf-tui"

for p in (str(LIB_DIR), str(TUI_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Textual is required for TUI tests — skip gracefully if absent
pytest.importorskip("textual", reason="python-textual not installed")


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
    theme_file.write_text(
        json.dumps(
            {
                "name": "test-theme",
                "background": "#1d2021",
                "foreground": "#ebdbb2",
                "accent": "#fabd2f",
                "comment": "#928374",
            }
        )
    )

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
    async with app.run_test(size=(120, 40)):
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
    async with app.run_test(size=(120, 40)):
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
        await pilot.press("tab")  # focus sidebar
        await pilot.press("enter")  # select first item
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
            OptionSelectScreen(
                title="Pick a value",
                options=[("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma")],
                current="beta",
            ),
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
            OptionSelectScreen(
                title="Pick a value",
                options=[("alpha", "alpha"), ("beta", "beta"), ("gamma", "gamma")],
                current="alpha",
            ),
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
        slider = SliderBar(
            min_val=0, max_val=1.0, value=0.9, step=0.1, fine_step=0.01, is_int=False
        )
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
    from unittest.mock import patch as _patch

    from textual.widgets import DataTable

    HyprconfApp = _get_app_class()
    app = HyprconfApp()

    # Patch sysfs and pgrep calls so the test is hermetic
    with (
        _patch("glob.iglob", return_value=iter([])),
        _patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
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
        async with app.run_test(size=(120, 40)):
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
async def test_on_unmount_logs_stderr_on_save_failure(patched_tui_env: Path, capsys) -> None:
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

    with (
        patch("main.save_pending", side_effect=_failing_save),
        patch("builtins.print", side_effect=_capture_print),
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            app._pending = {"general": {"border_size": "5"}}
            await pilot.press("q")

    assert any("auto-save" in msg.lower() or "WARNING" in msg for msg in stderr_msgs), (
        "on_unmount must print a warning to stderr when save_pending fails"
    )


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
    import inspect

    import main as tui_main

    src = inspect.getsource(tui_main.HyprconfApp.on_row_selected)
    # Old (buggy) pattern: split("=", 1)[1].strip()
    assert 'split("=", 1)[1]' not in src, (
        "TUI still uses unguarded split()[1] — IndexError regression"
    )
    # New pattern must check len before indexing
    assert "len(_parts) > 1" in src, "TUI must guard split result with len() check before indexing"


# ---------------------------------------------------------------------------
# Regression: _set_wallpaper must use hyprpaper IPC, not hyprctl keyword
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_wallpaper_uses_hyprpaper_ipc(
    patched_tui_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: _set_wallpaper must call `hyprctl hyprpaper wallpaper`
    (hyprpaper's own IPC), NOT `hyprctl keyword hyprpaper:wallpaper`."""
    import main as tui_main

    run_calls: list[list[str]] = []
    monkeypatch.setattr(
        tui_main, "_run", lambda args, **kw: (run_calls.append(list(args)), "ok")[1]
    )

    fake_wp = tmp_path / "bg.png"
    fake_wp.write_bytes(b"")

    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        app._set_wallpaper(fake_wp)
        await pilot.pause()

    # Must call hyprctl hyprpaper wallpaper …
    assert any(len(a) >= 3 and a[:3] == ["hyprctl", "hyprpaper", "wallpaper"] for a in run_calls), (
        "Expected `hyprctl hyprpaper wallpaper` call — hyprpaper has its own IPC"
    )
    # Must NOT call hyprctl keyword … hyprpaper …
    assert not any(
        len(a) >= 2
        and a[0] == "hyprctl"
        and a[1] == "keyword"
        and any("hyprpaper" in str(x) for x in a)
        for a in run_calls
    ), "`hyprctl keyword hyprpaper` is wrong — hyprpaper is not a Hyprland option section"


# ---------------------------------------------------------------------------
# Monitor position helper unit tests (pure Python, no TUI required)
# ---------------------------------------------------------------------------


def test_compute_logical_size_no_rotation():
    import main as tui_main

    lw, lh = tui_main._compute_logical_size(3840, 2160, 2.0, 0)
    assert lw == 1920.0
    assert lh == 1080.0


def test_compute_logical_size_swaps_axes_on_90_rotation():
    import main as tui_main

    # transform=1 means 90° — physical 1920x1080 becomes logical 540x960
    lw, lh = tui_main._compute_logical_size(1920, 1080, 2.0, 1)
    assert lw == 540.0
    assert lh == 960.0


def test_compute_logical_size_swaps_axes_on_270_rotation():
    import main as tui_main

    lw, lh = tui_main._compute_logical_size(1920, 1080, 1.0, 3)
    assert lw == 1080.0
    assert lh == 1920.0


def test_compute_logical_size_does_not_swap_on_180():
    import main as tui_main

    lw, lh = tui_main._compute_logical_size(1920, 1080, 1.0, 2)
    assert lw == 1920.0
    assert lh == 1080.0


def test_monitor_edit_screen_uses_file_position():
    """MonitorEditScreen should show the persisted file position, not hyprctl coords."""
    import main as tui_main

    mon = {
        "name": "HDMI-A-1",
        "width": 1920,
        "height": 1080,
        "refreshRate": 60.0,
        "scale": 1.0,
        "x": 1920,
        "y": 0,
        "transform": 0,
        "vrr": False,
        "availableModes": [],
    }
    screen = tui_main.MonitorEditScreen(mon, "", "auto-right")
    assert screen._pos == "auto-right"


def test_monitor_edit_screen_falls_back_to_hyprctl_coords():
    """When no file_position provided, fall back to the hyprctl x/y coordinates."""
    import main as tui_main

    mon = {
        "name": "HDMI-A-1",
        "width": 1920,
        "height": 1080,
        "refreshRate": 60.0,
        "scale": 1.0,
        "x": 1920,
        "y": 0,
        "transform": 0,
        "vrr": False,
        "availableModes": [],
    }
    screen = tui_main.MonitorEditScreen(mon, "")
    assert screen._pos == "1920x0"


def test_monitor_edit_screen_blank_new_defaults_to_auto():
    """Blank new-monitor dialog should default position to 'auto'."""
    import main as tui_main

    blank = {
        "name": "",
        "description": "",
        "width": 1920,
        "height": 1080,
        "refreshRate": 60.0,
        "scale": 1.0,
        "x": 0,
        "y": 0,
        "vrr": False,
        "availableModes": [],
    }
    screen = tui_main.MonitorEditScreen(blank, "", "auto")
    assert screen._pos == "auto"


def test_adjust_adjacent_no_change_when_delta_small():
    """No adjustment calls when logical size barely changes."""
    import main as tui_main

    upsert_calls: list = []
    run_calls: list = []

    snapshot = [
        {
            "name": "DP-1",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
        {
            "name": "HDMI-A-1",
            "x": 1920,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
    ]
    fake_file_mc = MagicMock()
    fake_file_mc.name = "HDMI-A-1"
    fake_file_mc.position = "1920x0"
    fake_file_mc.resolution = "1920x1080@60"
    fake_file_mc.scale = "1.0"
    fake_file_mc.extras = ""

    with (
        patch.object(tui_main, "_lib_monitor_configs", return_value=[fake_file_mc]),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_run", side_effect=lambda *a, **kw: run_calls.append(a)),
    ):
        # delta = 0 — no change
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 1920.0, 1080.0
        )

    assert upsert_calls == [], "no upsert expected for zero delta"
    assert run_calls == [], "no run expected for zero delta"


def test_adjust_adjacent_shifts_monitor_to_the_right():
    """When the edited monitor grows in width, the monitor to its right must be shifted."""
    import main as tui_main

    upsert_calls: list = []
    run_calls: list = []

    # DP-1 at origin (1920 logical wide); HDMI-A-1 butted against its right edge
    snapshot = [
        {
            "name": "DP-1",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
        {
            "name": "HDMI-A-1",
            "x": 1920,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
    ]
    fake_file_mc = MagicMock()
    fake_file_mc.name = "HDMI-A-1"
    fake_file_mc.position = "1920x0"
    fake_file_mc.resolution = "1920x1080@60"
    fake_file_mc.scale = "1.0"
    fake_file_mc.extras = ""

    with (
        patch.object(tui_main, "_lib_monitor_configs", return_value=[fake_file_mc]),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_run", side_effect=lambda *a, **kw: run_calls.append(a)),
    ):
        # DP-1 grew from 1920 to 2560 logical pixels wide (e.g. scale lowered)
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 2560.0, 1080.0
        )

    assert len(upsert_calls) == 1, "exactly one adjacent monitor should have been repositioned"
    # New position should be 2560x0 (shifted by +640)
    assert upsert_calls[0][2] == "2560x0"


def test_adjust_adjacent_skips_auto_positions():
    """Monitors with auto-* positions in monitors.conf must NOT be adjusted."""
    import main as tui_main

    upsert_calls: list = []

    snapshot = [
        {
            "name": "DP-1",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
        {
            "name": "HDMI-A-1",
            "x": 1920,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
    ]
    fake_file_mc = MagicMock()
    fake_file_mc.name = "HDMI-A-1"
    fake_file_mc.position = "auto-right"  # <-- auto, must be skipped
    fake_file_mc.resolution = "1920x1080@60"
    fake_file_mc.scale = "1.0"
    fake_file_mc.extras = ""

    with (
        patch.object(tui_main, "_lib_monitor_configs", return_value=[fake_file_mc]),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_run", return_value="ok"),
    ):
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 2560.0, 1080.0
        )

    assert upsert_calls == [], "auto-right monitor must not be adjusted"


def test_adjust_adjacent_handles_chain():
    """All monitors in a chain to the right of the edited one get the same delta."""
    import main as tui_main

    upsert_calls: list = []

    # Three monitors in a row: DP-1 (0), MON-B (1920), MON-C (3840)
    snapshot = [
        {
            "name": "DP-1",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
        {
            "name": "MON-B",
            "x": 1920,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
        {
            "name": "MON-C",
            "x": 3840,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
    ]
    fake_b = MagicMock(
        name="MON-B", position="1920x0", resolution="1920x1080@60", scale="1.0", extras=""
    )
    fake_b.name = "MON-B"
    fake_b.position = "1920x0"
    fake_b.resolution = "1920x1080@60"
    fake_b.scale = "1.0"
    fake_b.extras = ""
    fake_c = MagicMock()
    fake_c.name = "MON-C"
    fake_c.position = "3840x0"
    fake_c.resolution = "1920x1080@60"
    fake_c.scale = "1.0"
    fake_c.extras = ""

    with (
        patch.object(tui_main, "_lib_monitor_configs", return_value=[fake_b, fake_c]),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_run", return_value="ok"),
    ):
        # DP-1 grows from 1920 to 2560 → delta +640
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 2560.0, 1080.0
        )

    positions = {c[0]: c[2] for c in upsert_calls}
    assert positions.get("MON-B") == "2560x0", "MON-B should shift by +640"
    assert positions.get("MON-C") == "4480x0", "MON-C should shift by +640"


def test_adjust_adjacent_shifts_monitor_below():
    """When the edited monitor grows in height, the monitor below it must be shifted."""
    import main as tui_main

    upsert_calls: list = []

    snapshot = [
        {
            "name": "DP-1",
            "x": 0,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
        {
            "name": "HDMI-A-1",
            "x": 0,
            "y": 1080,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
            "transform": 0,
        },
    ]
    fake_file_mc = MagicMock()
    fake_file_mc.name = "HDMI-A-1"
    fake_file_mc.position = "0x1080"
    fake_file_mc.resolution = "1920x1080@60"
    fake_file_mc.scale = "1.0"
    fake_file_mc.extras = ""

    with (
        patch.object(tui_main, "_lib_monitor_configs", return_value=[fake_file_mc]),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_run", return_value="ok"),
    ):
        # DP-1 grew from 1080 to 1440 logical pixels tall
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 1920.0, 1440.0
        )

    assert len(upsert_calls) == 1
    assert upsert_calls[0][2] == "0x1440"


# ---------------------------------------------------------------------------
# KeybindEditScreen: save / cancel / validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keybind_edit_screen_saves(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.KeybindEditScreen(
                kind="bind", mods="SUPER", key="T", dispatcher="exec", args="kitty"
            ),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        # Submitting the last field commits the whole keybind.
        app.screen.query_one("#kb-args", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert received == [("bind", "SUPER", "T", "exec", "kitty")]


@pytest.mark.asyncio
async def test_keybind_edit_screen_cancel(patched_tui_env: Path) -> None:
    import main as tui_main

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.KeybindEditScreen(kind="bind", key="T", dispatcher="exec"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert received == [None]


@pytest.mark.asyncio
async def test_keybind_edit_screen_requires_key_and_dispatcher(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.KeybindEditScreen(kind="bind", mods="SUPER", key="", dispatcher=""),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#kb-args", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Missing key + dispatcher → validation blocks the dismiss; modal stays open.
        assert received == []
        assert isinstance(app.screen, tui_main.KeybindEditScreen)


# ---------------------------------------------------------------------------
# RuleEditScreen: window + workspace save, cancel, validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_edit_window_saves(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.RuleEditScreen(
                rule_type="window", action="float", filter1="class:kitty", filter2=""
            ),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#rule-filter2", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert received == [("window", "float", ["class:kitty"])]


@pytest.mark.asyncio
async def test_rule_edit_workspace_saves(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.RuleEditScreen(
                rule_type="workspace", wksp_id="2", wksp_opts="monitor:HDMI-A-1, default:true"
            ),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#wksp-opts", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert received == [("workspace", "2", "monitor:HDMI-A-1, default:true")]


@pytest.mark.asyncio
async def test_rule_edit_cancel(patched_tui_env: Path) -> None:
    import main as tui_main

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.RuleEditScreen(rule_type="window", action="float"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert received == [None]


@pytest.mark.asyncio
async def test_rule_edit_window_requires_action(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 30)) as pilot:
        await app.push_screen(
            tui_main.RuleEditScreen(rule_type="window", action="", filter1="class:kitty"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#rule-filter2", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Empty action → validation blocks the dismiss; modal stays open.
        assert received == []
        assert isinstance(app.screen, tui_main.RuleEditScreen)


# ---------------------------------------------------------------------------
# Special sections render hermetically: hyprpaper / hyprlock / hypridle / theme
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hyprpaper_section_renders(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable

    (patched_tui_env / "hyprpaper.conf").write_text(
        "preload = ~/wallpaper/a.jpg\nwallpaper = eDP-1,~/wallpaper/a.jpg\n"
    )
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._load_section("hyprpaper")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert table.row_count > 0
        flat = " ".join(str(c) for i in range(table.row_count) for c in table.get_row_at(i))
        assert "a.jpg" in flat or "wallpaper" in flat.lower()


@pytest.mark.asyncio
async def test_hyprlock_section_renders(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable

    (patched_tui_env / "hyprlock.conf").write_text(
        "background {\n    monitor =\n    color = rgba(0,0,0,1.0)\n}\n"
    )
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._load_section("hyprlock")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert table.row_count > 0


@pytest.mark.asyncio
async def test_hypridle_section_renders(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable

    (patched_tui_env / "hypridle.conf").write_text(
        "listener {\n    timeout = 300\n    on-timeout = loginctl lock-session\n}\n"
    )
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._load_section("hypridle")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert table.row_count > 0


@pytest.mark.asyncio
async def test_theme_section_renders(
    patched_tui_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main as tui_main
    from textual.widgets import DataTable

    monkeypatch.setattr(tui_main, "list_themes", lambda: ["acme-dark", "acme-light"])
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._load_section("theme")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert table.row_count == 2


# ---------------------------------------------------------------------------
# EditScreen + NumericEditScreen: option value save-paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_screen_saves(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(
            tui_main.EditScreen(
                section="general",
                key="layout",
                current="dwindle",
                type_="enum:dwindle,master",
                default="dwindle",
                description="Active layout",
            ),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#edit-input", Input).value = "master"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert received == ["master"]


@pytest.mark.asyncio
async def test_edit_screen_cancel(patched_tui_env: Path) -> None:
    import main as tui_main

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(
            tui_main.EditScreen(
                section="general",
                key="border_size",
                current="2",
                type_="int",
                default="1",
                description="Border width",
            ),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert received == [None]


def _numeric_screen(tui_main, *, current="5", min_val=0, max_val=100):
    return tui_main.NumericEditScreen(
        section="general",
        key="gaps_in",
        current=current,
        type_="int",
        default="5",
        description="Inner gaps",
        min_val=min_val,
        max_val=max_val,
        step=1,
        fine_step=1,
    )


@pytest.mark.asyncio
async def test_numeric_edit_screen_saves(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(_numeric_screen(tui_main), callback=lambda v: received.append(v))
        await pilot.pause()
        inp = app.screen.query_one("#slider-input", Input)
        inp.value = "42"
        inp.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert received == ["42"]


@pytest.mark.asyncio
async def test_numeric_edit_screen_clamps_to_max(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(
            _numeric_screen(tui_main, max_val=10), callback=lambda v: received.append(v)
        )
        await pilot.pause()
        inp = app.screen.query_one("#slider-input", Input)
        inp.value = "999"
        inp.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    # _apply clamps to the configured max before dismissing
    assert received == ["10"]


@pytest.mark.asyncio
async def test_numeric_edit_screen_cancel(patched_tui_env: Path) -> None:
    import main as tui_main

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(_numeric_screen(tui_main), callback=lambda v: received.append(v))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert received == [None]
