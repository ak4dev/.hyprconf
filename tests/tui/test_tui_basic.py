"""
TUI smoke tests using Textual's built-in App.run_test() + Pilot framework.

These tests exercise the TUI in fully headless mode — no terminal, no
Hyprland session, no Omarchy binaries and no display required.  They are
safe to run in CI.

Design principles:
- Each test is narrow: it verifies ONE behaviour.
- Pilot actions are kept minimal — we test state, not keypress sequences.
- Heavy monkeypatching keeps external deps (hyprctl, omarchy-*, file I/O)
  isolated: every Omarchy seam goes through lib.omarchy, which is patched here
  — the real binaries are never run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — TUI lives outside the lib tree
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
LIB_DIR = REPO_ROOT / "lib"
TUI_DIR = REPO_ROOT / "tui"

for p in (str(LIB_DIR), str(TUI_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Textual is required for TUI tests — skip gracefully if absent
pytest.importorskip("textual", reason="python-textual not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_MONITOR = {
    "name": "HDMI-A-1",
    "description": "Test Monitor",
    "width": 1920,
    "height": 1080,
    "refreshRate": 60.0,
    "scale": 1.0,
    "x": 0,
    "y": 0,
    "transform": 0,
    "vrr": False,
    "availableModes": [],
}


@pytest.fixture()
def patched_tui_env(hypr_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Patch all external calls the TUI makes on startup."""
    # Hyprland not active → TUI falls back to file-only mode gracefully
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.setattr("hyprconf.hyprctl.is_active", lambda: False)
    # Keep every $HOME-derived Omarchy path (colors.toml, shell.json, …) off
    # the real home.
    monkeypatch.setenv("HOME", str(tmp_path))

    import main as tui_main
    from hyprconf import omarchy

    monkeypatch.setattr(tui_main, "HYPRLAND_ACTIVE", False)
    # The TUI binds these file paths at import time; point them at the
    # fixture tree so no test reads or writes the real ~/.config/hypr.
    monkeypatch.setattr(tui_main, "KEYBINDS_CONF", hypr_dir / "bindings.lua")
    monkeypatch.setattr(tui_main, "HYPRLAND_CONF", hypr_dir / "hyprland.lua")
    monkeypatch.setattr(tui_main, "MONITORS_FILE", hypr_dir / "monitors.lua")
    monkeypatch.setattr(tui_main, "OVERRIDES_FILE", hypr_dir / "conf.d" / "local.lua")
    # Monitors come from hyprctl; MonitorEditScreen must open without IPC.
    monkeypatch.setattr(tui_main, "_lib_get_monitors", lambda: [dict(TEST_MONITOR)])

    # Omarchy seams — the TUI reads/applies through lib.omarchy only.
    monkeypatch.setattr(omarchy, "current_theme", lambda run=None: "Test Theme")
    monkeypatch.setattr(omarchy, "list_themes", lambda run=None: ["Acme Dark", "Test Theme"])
    monkeypatch.setattr(omarchy, "set_theme", lambda name, run=None: True)
    monkeypatch.setattr(omarchy, "list_backgrounds", lambda: [])
    monkeypatch.setattr(omarchy, "current_background", lambda: None)
    monkeypatch.setattr(omarchy, "set_background", lambda path, run=None: True)
    monkeypatch.setattr(omarchy, "idle_timeouts", lambda: {"lock": 300, "screensaver": 150})
    monkeypatch.setattr(
        omarchy, "set_idle_timeouts", lambda lock=None, screensaver=None, run=None: True
    )
    monkeypatch.setattr(omarchy, "stay_awake", lambda run=None: False)
    monkeypatch.setattr(omarchy, "toggle_stay_awake", lambda run=None: True)

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


def _rows(table) -> list[list[str]]:
    return [[str(c) for c in table.get_row_at(i)] for i in range(table.row_count)]


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


@pytest.mark.asyncio
async def test_brand_bar_shows_omarchy_theme(patched_tui_env: Path) -> None:
    """The [theme: …] readout comes from omarchy-theme-current (lib.omarchy)."""
    from textual.widgets import Static

    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)):
        assert "Test Theme" in str(app.query_one("#brand-right", Static).render())


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


@pytest.mark.asyncio
async def test_sidebar_lists_omarchy_sections_not_standalone_ones(patched_tui_env: Path) -> None:
    """hypridle/hyprlock/hyprpaper are not installed under Omarchy (its idle,
    lock and background are quickshell services) and the standalone hardware
    section is gone; the Omarchy-native sections take their place."""
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)):
        ids = {item.id for item in app.query("#section-list ListItem")}
        assert {"sec-theme", "sec-background", "sec-idle"} <= ids
        assert not ids & {"sec-hyprlock", "sec-hypridle", "sec-hyprpaper", "sec-hardware"}


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

    mon = {**TEST_MONITOR, "x": 1920}
    screen = tui_main.MonitorEditScreen(mon, "", "auto-right")
    assert screen._pos == "auto-right"


def test_monitor_edit_screen_falls_back_to_hyprctl_coords():
    """When no file_position provided, fall back to the hyprctl x/y coordinates."""
    import main as tui_main

    mon = {**TEST_MONITOR, "x": 1920}
    screen = tui_main.MonitorEditScreen(mon, "")
    assert screen._pos == "1920x0"


def test_monitor_edit_screen_blank_new_defaults_to_auto():
    """Blank new-monitor dialog should default position to 'auto'."""
    import main as tui_main

    blank = {**TEST_MONITOR, "name": "", "description": ""}
    screen = tui_main.MonitorEditScreen(blank, "", "auto")
    assert screen._pos == "auto"


def _snapshot(*mons: tuple[str, int, int]) -> list[dict]:
    return [
        {"name": n, "x": x, "y": y, "width": 1920, "height": 1080, "scale": 1.0, "transform": 0}
        for n, x, y in mons
    ]


def _file_mc(name: str, position: str) -> MagicMock:
    mc = MagicMock()
    mc.name = name
    mc.position = position
    mc.resolution = "1920x1080@60"
    mc.scale = "1.0"
    mc.extras = ""
    return mc


def test_adjust_adjacent_no_change_when_delta_small():
    """No adjustment calls when logical size barely changes."""
    import main as tui_main

    upsert_calls: list = []
    apply_calls: list = []
    snapshot = _snapshot(("DP-1", 0, 0), ("HDMI-A-1", 1920, 0))

    with (
        patch.object(
            tui_main, "_lib_monitor_configs", return_value=[_file_mc("HDMI-A-1", "1920x0")]
        ),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(
            tui_main, "_lib_apply_monitor", side_effect=lambda *a, **kw: apply_calls.append(a)
        ),
    ):
        # delta = 0 — no change
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 1920.0, 1080.0
        )

    assert upsert_calls == [], "no upsert expected for zero delta"
    assert apply_calls == [], "no live apply expected for zero delta"


def test_adjust_adjacent_shifts_monitor_to_the_right():
    """When the edited monitor grows in width, the monitor to its right must be
    shifted — in monitors.lua and live, through the lib's hl.monitor eval."""
    import main as tui_main

    upsert_calls: list = []
    apply_calls: list = []
    # DP-1 at origin (1920 logical wide); HDMI-A-1 butted against its right edge
    snapshot = _snapshot(("DP-1", 0, 0), ("HDMI-A-1", 1920, 0))

    with (
        patch.object(
            tui_main, "_lib_monitor_configs", return_value=[_file_mc("HDMI-A-1", "1920x0")]
        ),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(
            tui_main, "_lib_apply_monitor", side_effect=lambda *a, **kw: apply_calls.append(a)
        ),
    ):
        # DP-1 grew from 1920 to 2560 logical pixels wide (e.g. scale lowered)
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 2560.0, 1080.0
        )

    assert len(upsert_calls) == 1, "exactly one adjacent monitor should have been repositioned"
    # New position should be 2560x0 (shifted by +640)
    assert upsert_calls[0][2] == "2560x0"
    assert apply_calls == [("HDMI-A-1", "1920x1080@60", "2560x0", "1.0", "")]


def test_adjust_adjacent_skips_auto_positions():
    """Monitors with auto-* positions in monitors.lua must NOT be adjusted."""
    import main as tui_main

    upsert_calls: list = []
    snapshot = _snapshot(("DP-1", 0, 0), ("HDMI-A-1", 1920, 0))

    with (
        patch.object(
            tui_main, "_lib_monitor_configs", return_value=[_file_mc("HDMI-A-1", "auto-right")]
        ),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_lib_apply_monitor", return_value=True),
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
    snapshot = _snapshot(("DP-1", 0, 0), ("MON-B", 1920, 0), ("MON-C", 3840, 0))

    with (
        patch.object(
            tui_main,
            "_lib_monitor_configs",
            return_value=[_file_mc("MON-B", "1920x0"), _file_mc("MON-C", "3840x0")],
        ),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_lib_apply_monitor", return_value=True),
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
    snapshot = _snapshot(("DP-1", 0, 0), ("HDMI-A-1", 0, 1080))

    with (
        patch.object(
            tui_main, "_lib_monitor_configs", return_value=[_file_mc("HDMI-A-1", "0x1080")]
        ),
        patch.object(
            tui_main, "_lib_upsert_monitor", side_effect=lambda *a, **kw: upsert_calls.append(a)
        ),
        patch.object(tui_main, "_lib_apply_monitor", return_value=True),
    ):
        # DP-1 grew from 1080 to 1440 logical pixels tall
        tui_main._adjust_adjacent_monitor_positions(
            "DP-1", snapshot, 1920.0, 1080.0, 1920.0, 1440.0
        )

    assert len(upsert_calls) == 1
    assert upsert_calls[0][2] == "0x1440"


def test_apply_monitor_keyword_applies_persists_and_reports():
    """The blocking apply step: hl.monitor eval + monitors.lua upsert, in that order."""
    import main as tui_main

    calls: list = []
    with (
        patch.object(
            tui_main,
            "_lib_apply_monitor",
            side_effect=lambda *a: (calls.append(("apply", a)), True)[1],
        ),
        patch.object(
            tui_main,
            "_lib_upsert_monitor",
            side_effect=lambda **kw: (calls.append(("upsert", kw)), True)[1],
        ),
        patch.object(tui_main, "_lib_monitor_configs", return_value=[]),
    ):
        msg, severity = tui_main._apply_monitor_keyword(
            "HDMI-A-1,1920x1080@60.00,auto-right,1.0, vrr, 1", dict(TEST_MONITOR), []
        )
    assert severity == "information"
    assert "HDMI-A-1" in msg
    assert calls == [
        ("apply", ("HDMI-A-1", "1920x1080@60.00", "auto-right", "1.0", "vrr, 1")),
        (
            "upsert",
            {
                "name": "HDMI-A-1",
                "resolution": "1920x1080@60.00",
                "position": "auto-right",
                "scale": "1.0",
                "extras": "vrr, 1",
            },
        ),
    ]


def test_apply_monitor_keyword_rejects_short_spec():
    import main as tui_main

    with patch.object(tui_main, "_lib_apply_monitor") as apply:
        msg, severity = tui_main._apply_monitor_keyword("HDMI-A-1,disable", None, [])
    assert severity == "error"
    apply.assert_not_called()


# ---------------------------------------------------------------------------
# MonitorEditScreen: Enter-to-apply backs out exactly once (regression)
#
# The editor's dismiss callback used to run hyprctl/persist/adjust/refresh on
# the UI thread; the freeze buffered a second Enter, which then landed on the
# monitors table and re-pushed a fresh MonitorEditScreen. The apply now runs
# off the UI thread and the table ignores a RowSelected in the reopen guard.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitor_edit_single_enter_dismisses_with_keyword(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(100, 50)) as pilot:
        await app.push_screen(
            tui_main.MonitorEditScreen(dict(TEST_MONITOR), "", "auto-right"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#mon-mirror", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert not isinstance(app.screen, tui_main.MonitorEditScreen)

    assert received == ["HDMI-A-1,1920x1080@60.00,auto-right,1.0, vrr, 0"]


@pytest.mark.asyncio
async def test_monitor_edit_ctrl_s_applies_from_any_field(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(100, 50)) as pilot:
        await app.push_screen(
            tui_main.MonitorEditScreen(dict(TEST_MONITOR), "", "auto-right"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#mon-scale", Input).focus()  # first field, not the last
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert received == ["HDMI-A-1,1920x1080@60.00,auto-right,1.0, vrr, 0"]


@pytest.mark.asyncio
async def test_monitor_edit_double_enter_applies_once_and_backs_out(
    patched_tui_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main as tui_main
    from textual.widgets import Input

    apply_calls: list = []
    upsert_calls: list = []
    monkeypatch.setattr(tui_main, "get_monitors", lambda: [dict(TEST_MONITOR)])
    monkeypatch.setattr(tui_main, "_lib_monitor_configs", lambda *a, **kw: [])
    monkeypatch.setattr(
        tui_main, "_lib_upsert_monitor", lambda **kw: (upsert_calls.append(kw), True)[1]
    )
    monkeypatch.setattr(tui_main, "_lib_apply_monitor", lambda *a: (apply_calls.append(a), True)[1])

    HyprconfApp = _get_app_class()
    app = HyprconfApp(initial_section="monitors", slim=True)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # the table row → opens the editor
        await pilot.pause()
        assert isinstance(app.screen, tui_main.MonitorEditScreen)
        app.screen.query_one("#mon-mirror", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.press("enter")  # the double-press that used to reopen the editor
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not isinstance(app.screen, tui_main.MonitorEditScreen)
        assert len(app.screen_stack) == 1

    assert len(apply_calls) == 1, apply_calls
    assert len(upsert_calls) == 1, upsert_calls
    assert apply_calls[0][0] == "HDMI-A-1"


@pytest.mark.asyncio
async def test_monitor_edit_escape_cancels_without_apply(
    patched_tui_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main as tui_main

    apply_calls: list = []
    monkeypatch.setattr(tui_main, "_lib_apply_monitor", lambda *a: (apply_calls.append(a), True)[1])
    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(100, 50)) as pilot:
        await app.push_screen(
            tui_main.MonitorEditScreen(dict(TEST_MONITOR), "", "auto-right"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        await app.workers.wait_for_complete()

    assert received == [None]
    assert apply_calls == []


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
    async with app.run_test(size=(80, 34)) as pilot:
        await app.push_screen(
            tui_main.KeybindEditScreen(
                kind="bind",
                mods="SUPER",
                key="T",
                dispatcher="exec",
                args="kitty",
                description="Terminal",
            ),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        # Submitting the last field (the description) commits the whole keybind.
        app.screen.query_one("#kb-desc", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert received == [("bind", "SUPER", "T", "exec", "kitty", "Terminal")]


@pytest.mark.asyncio
async def test_keybind_edit_screen_ctrl_s_applies(patched_tui_env: Path) -> None:
    import main as tui_main
    from textual.widgets import Input

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 34)) as pilot:
        await app.push_screen(
            tui_main.KeybindEditScreen(kind="bind", mods="SUPER", key="T", dispatcher="exec"),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#kb-mods", Input).focus()
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert received == [("bind", "SUPER", "T", "exec", "", "")]


@pytest.mark.asyncio
async def test_keybind_edit_screen_cancel(patched_tui_env: Path) -> None:
    import main as tui_main

    HyprconfApp = _get_app_class()
    received: list = []

    app = HyprconfApp()
    async with app.run_test(size=(80, 34)) as pilot:
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
    async with app.run_test(size=(80, 34)) as pilot:
        await app.push_screen(
            tui_main.KeybindEditScreen(kind="bind", mods="SUPER", key="", dispatcher=""),
            callback=lambda v: received.append(v),
        )
        await pilot.pause()
        app.screen.query_one("#kb-desc", Input).focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Missing key + dispatcher → validation blocks the dismiss; modal stays open.
        assert received == []
        assert isinstance(app.screen, tui_main.KeybindEditScreen)


@pytest.mark.asyncio
async def test_keybinds_section_shows_description_column(patched_tui_env: Path) -> None:
    """bindings.lua's o.bind/rebind descriptions are a column of their own."""
    from textual.widgets import DataTable

    (patched_tui_env / "bindings.lua").write_text(
        'local mainMod = "SUPER"\n'
        'o.bind(mainMod .. " + SHIFT + Q", "Log out", "omarchy-system-logout")\n'
        'rebind(mainMod .. " + T", "Terminal", hl.dsp.exec_cmd("omarchy-launch-terminal"))\n'
    )
    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(140, 40)) as pilot:
        app._load_section("keybinds")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        assert [str(c.label) for c in table.columns.values()][-1] == "DESCRIPTION"
        rows = _rows(table)
        assert rows[0][-1] == "Log out"
        assert rows[1][-1] == "Terminal"
        assert rows[1][3:5] == ["exec_cmd", "omarchy-launch-terminal"]


@pytest.mark.asyncio
async def test_new_keybind_is_written_as_o_bind(patched_tui_env: Path) -> None:
    """[n] on the keybinds section appends an o.bind line — the description is
    what gets it into Omarchy's SUPER+K menu."""
    import main as tui_main
    from textual.widgets import Input

    kb = patched_tui_env / "bindings.lua"
    HyprconfApp = _get_app_class()
    app = HyprconfApp(initial_section="keybinds", slim=True)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, tui_main.KeybindEditScreen)
        app.screen.query_one("#kb-key", Input).value = "B"
        app.screen.query_one("#kb-disp", Input).value = "exec"
        app.screen.query_one("#kb-args", Input).value = "omarchy-launch-browser"
        app.screen.query_one("#kb-desc", Input).value = "Browser"
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert 'o.bind("B", "Browser", "omarchy-launch-browser")' in kb.read_text()


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
# Omarchy-native sections: theme / background / idle — driven through
# monkeypatched lib.omarchy functions, never the real omarchy-* binaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_theme_section_renders(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable

    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._load_section("theme")
        await pilot.pause()
        table = app.query_one("#option-table", DataTable)
        rows = _rows(table)
        assert [r[0] for r in rows] == ["Acme Dark", "Test Theme"]
        assert "active" in rows[1][1] and "active" not in rows[0][1]


@pytest.mark.asyncio
async def test_theme_enter_applies_via_omarchy_theme_set(
    patched_tui_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hyprconf import omarchy
    from textual.widgets import Static

    applied: list[str] = []
    monkeypatch.setattr(
        omarchy, "set_theme", lambda name, run=None: (applied.append(name), True)[1]
    )

    HyprconfApp = _get_app_class()
    app = HyprconfApp(initial_section="theme", slim=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # row 0: "Acme Dark"
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "Acme Dark" in str(app.query_one("#brand-right", Static).render())

    assert applied == ["Acme Dark"]


@pytest.mark.asyncio
async def test_background_section_renders_and_applies(
    patched_tui_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hyprconf import omarchy
    from textual.widgets import DataTable

    a = tmp_path / ".config" / "omarchy" / "backgrounds" / "t" / "a.jpg"
    b = tmp_path / ".local" / "state" / "omarchy" / "current" / "theme" / "backgrounds" / "b.png"
    monkeypatch.setattr(omarchy, "list_backgrounds", lambda: [a, b])
    monkeypatch.setattr(omarchy, "current_background", lambda: a)
    applied: list[str] = []
    monkeypatch.setattr(
        omarchy, "set_background", lambda path, run=None: (applied.append(str(path)), True)[1]
    )

    HyprconfApp = _get_app_class()
    app = HyprconfApp(initial_section="background", slim=True)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        rows = _rows(app.query_one("#option-table", DataTable))
        assert [r[0] for r in rows] == [
            "~/.config/omarchy/backgrounds/t/a.jpg",
            "~/.local/state/omarchy/current/theme/backgrounds/b.png",
        ]
        assert "active" in rows[0][1] and "active" not in rows[1][1]
        await pilot.press("down")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    assert applied == [str(b)]


@pytest.mark.asyncio
async def test_idle_section_renders_shell_json_timeouts(patched_tui_env: Path) -> None:
    from textual.widgets import DataTable

    HyprconfApp = _get_app_class()
    app = HyprconfApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._load_section("idle")
        await pilot.pause()
        rows = _rows(app.query_one("#option-table", DataTable))
        assert [(r[0], r[1]) for r in rows] == [
            ("Lock after (s)", "300"),
            ("Screensaver after (s)", "150"),
            ("Stay awake", "off"),
        ]


@pytest.mark.asyncio
async def test_idle_lock_timeout_edit_persists_via_set_idle_timeouts(
    patched_tui_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main as tui_main
    from hyprconf import omarchy
    from textual.widgets import Input

    written: list[dict] = []

    def _fake_set(lock=None, screensaver=None, run=None):
        written.append({"lock": lock, "screensaver": screensaver})
        return True

    monkeypatch.setattr(omarchy, "set_idle_timeouts", _fake_set)

    HyprconfApp = _get_app_class()
    app = HyprconfApp(initial_section="idle", slim=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # row 0: Lock after (s)
        await pilot.pause()
        assert isinstance(app.screen, tui_main.NumericEditScreen)
        inp = app.screen.query_one("#slider-input", Input)
        inp.value = "600"
        inp.focus()
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    assert written == [{"lock": 600, "screensaver": None}]


@pytest.mark.asyncio
async def test_idle_stay_awake_row_toggles_via_omarchy_toggle_idle(
    patched_tui_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hyprconf import omarchy
    from textual.widgets import DataTable

    state = {"awake": False}
    monkeypatch.setattr(omarchy, "stay_awake", lambda run=None: state["awake"])

    def _toggle(run=None):
        state["awake"] = not state["awake"]
        return state["awake"]

    monkeypatch.setattr(omarchy, "toggle_stay_awake", _toggle)

    HyprconfApp = _get_app_class()
    app = HyprconfApp(initial_section="idle", slim=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("enter")  # row 2: Stay awake
        await app.workers.wait_for_complete()
        await pilot.pause()
        rows = _rows(app.query_one("#option-table", DataTable))
        assert rows[2][:2] == ["Stay awake", "on"]

    assert state["awake"] is True


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
