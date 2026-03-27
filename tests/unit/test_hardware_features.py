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
    monkeypatch.setattr(st, "update_btop", lambda *_a, **_k: None)
    monkeypatch.setattr(st, "update_touch_panel", lambda _: None)
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
    monkeypatch.setattr(st, "update_btop", lambda *_a, **_k: None)
    monkeypatch.setattr(st, "update_touch_panel", lambda _: None)
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


# ---------------------------------------------------------------------------
# Touchscreen detection — standard + Wacom I2C Finger path
# ---------------------------------------------------------------------------

def _run_touchscreen_detection(uevent_files: dict) -> bool:
    """
    Reimplementation of the shared _has_touchscreen() logic for unit testing.
    uevent_files: {path_str: content_str}
    """
    for content in uevent_files.values():
        if "ID_INPUT_TOUCHSCREEN=1" in content:
            return True
        if "ID_INPUT_TOUCH=1" in content:
            return True
        if ('NAME="Wacom' in content and 'Finger' in content
                and 'PHYS="i2c-' in content):
            return True
    return False


def test_touchscreen_detected_via_standard_udev_tag():
    files = {
        "/sys/class/input/event0/device/uevent": (
            "NAME=\"ELAN Touchscreen\"\nPHYS=\"i2c-ELAN0001:00\"\n"
            "ID_INPUT=1\nID_INPUT_TOUCHSCREEN=1\n"
        )
    }
    assert _run_touchscreen_detection(files) is True


def test_touchscreen_detected_via_id_input_touch():
    """Devices like ASUS ROG Ally use ID_INPUT_TOUCH=1 instead of ID_INPUT_TOUCHSCREEN=1."""
    files = {
        "/sys/class/input/event0/device/uevent": (
            "NAME=\"ILITEK ILITEK-TP\"\nPHYS=\"usb-0000:c4:00.3-3/input0\"\n"
            "ID_INPUT=1\nID_INPUT_TOUCH=1\n"
        )
    }
    assert _run_touchscreen_detection(files) is True


def test_touchscreen_not_detected_when_absent():
    files = {
        "/sys/class/input/event0/device/uevent": (
            "NAME=\"AT Translated Set 2 keyboard\"\n"
            "ID_INPUT=1\nID_INPUT_KEY=1\n"
        )
    }
    assert _run_touchscreen_detection(files) is False


def test_touchscreen_detected_via_wacom_i2c_finger():
    """ThinkPad X13 Yoga Gen 3: Wacom I2C HID touch layer — no ID_INPUT_TOUCHSCREEN."""
    files = {
        "/sys/class/input/event8/device/uevent": (
            "PRODUCT=18/56a/5288/100\nNAME=\"Wacom HID 5288 Pen\"\n"
            "PHYS=\"i2c-WACF2200:00\"\n"
        ),
        "/sys/class/input/event9/device/uevent": (
            "PRODUCT=18/56a/5288/100\nNAME=\"Wacom HID 5288 Finger\"\n"
            "PHYS=\"i2c-WACF2200:00\"\n"
            "ABS=260800000000003\n"
        ),
    }
    assert _run_touchscreen_detection(files) is True


def test_wacom_pen_alone_does_not_trigger_touchscreen():
    """Pen-only node must not count as a touchscreen."""
    files = {
        "/sys/class/input/event8/device/uevent": (
            "PRODUCT=18/56a/5288/100\nNAME=\"Wacom HID 5288 Pen\"\n"
            "PHYS=\"i2c-WACF2200:00\"\n"
        ),
    }
    assert _run_touchscreen_detection(files) is False


def test_usb_wacom_tablet_does_not_trigger_touchscreen():
    """External USB Wacom tablet with a Finger node must not trigger detection."""
    files = {
        "/sys/class/input/event3/device/uevent": (
            "NAME=\"Wacom Intuos Pro M Finger\"\n"
            "PHYS=\"usb-0000:00:14.0-3/input1\"\n"
        ),
    }
    assert _run_touchscreen_detection(files) is False


# ---------------------------------------------------------------------------
# update_touch_panel() — switch_theme.py
# ---------------------------------------------------------------------------

def test_update_touch_panel_writes_colors_file(tmp_path, monkeypatch):
    colors_file = tmp_path / ".config" / "touch-panel" / "colors"
    monkeypatch.setattr(st, "TOUCH_PANEL_COLORS_FILE", str(colors_file))
    st.update_touch_panel(DARK_THEME)
    assert colors_file.exists()
    content = colors_file.read_text()
    assert '#1e1e2e' in content
    assert '#cdd6f4' in content
    assert '#89b4fa' in content


def test_update_touch_panel_creates_config_dir(tmp_path, monkeypatch):
    colors_file = tmp_path / ".config" / "touch-panel" / "colors"
    monkeypatch.setattr(st, "TOUCH_PANEL_COLORS_FILE", str(colors_file))
    st.update_touch_panel(DARK_THEME)
    assert (tmp_path / ".config" / "touch-panel").is_dir()


def test_update_touch_panel_skips_when_no_background(tmp_path, monkeypatch):
    colors_file = tmp_path / ".config" / "touch-panel" / "colors"
    monkeypatch.setattr(st, "TOUCH_PANEL_COLORS_FILE", str(colors_file))
    st.update_touch_panel({})
    assert not colors_file.exists()


def test_update_touch_panel_signals_running_panel(tmp_path, monkeypatch):
    colors_file = tmp_path / ".config" / "touch-panel" / "colors"
    monkeypatch.setattr(st, "TOUCH_PANEL_COLORS_FILE", str(colors_file))
    fake_pid = "12345"
    kill_calls = []

    def fake_run(cmd, **_kwargs):
        m = MagicMock()
        if cmd[0] == "pgrep":
            m.returncode = 0
            m.stdout = fake_pid + "\n"
        else:
            m.returncode = 0
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    import signal
    st.update_touch_panel(DARK_THEME)
    assert (12345, signal.SIGUSR1) in kill_calls


def test_update_touch_panel_no_signal_when_not_running(tmp_path, monkeypatch):
    colors_file = tmp_path / ".config" / "touch-panel" / "colors"
    monkeypatch.setattr(st, "TOUCH_PANEL_COLORS_FILE", str(colors_file))
    kill_calls = []

    def fake_run(cmd, **_kwargs):
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    st.update_touch_panel(DARK_THEME)
    assert kill_calls == []


# ---------------------------------------------------------------------------
# write_hardware_conf() — device block generation
# ---------------------------------------------------------------------------

SETUP_SH = Path(__file__).parent.parent.parent / "setup.sh"

def _run_write_hardware_conf(
    tmp_path: Path,
    *,
    has_touch: bool = False,
    has_accel: bool = False,
    has_nvidia: bool = False,
) -> str:
    """
    Run write_hardware_conf() (extracted from setup.sh) with stubbed helpers.
    Returns the text of the generated 60-hardware.conf.
    """
    source = SETUP_SH.read_text()

    def _extract_func(src: str, name: str) -> str:
        start = src.find(f"{name}()")
        assert start != -1, f"{name}() not found in setup.sh"
        end = src.find("\n}", start)
        return src[src.rfind("\n", 0, start) + 1: end + 2]

    write_func = _extract_func(source, "write_hardware_conf")

    conf_dir = tmp_path / ".config" / "hypr" / "conf.d"
    conf_dir.mkdir(parents=True)

    script = f"""
set -euo pipefail
HOME="{tmp_path}"
_has_touchscreen()   {{ {'return 0' if has_touch  else 'return 1'}; }}
_has_accelerometer() {{ {'return 0' if has_accel  else 'return 1'}; }}
_has_nvidia()        {{ {'return 0' if has_nvidia else 'return 1'}; }}
log_ok() {{ :; }}
{write_func}
write_hardware_conf
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, f"write_hardware_conf failed:\n{result.stderr}"
    return (conf_dir / "60-hardware.conf").read_text()


def test_write_hardware_conf_no_touchdevice_block_without_touchscreen(tmp_path):
    conf = _run_write_hardware_conf(tmp_path, has_touch=False)
    assert "touchdevice" not in conf


def test_write_hardware_conf_emits_touchdevice_block_with_touchscreen(tmp_path):
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    assert "touchdevice" in conf


def test_write_hardware_conf_touchdevice_output_is_edp1(tmp_path):
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    assert "output    = eDP-1" in conf


def test_write_hardware_conf_touchdevice_transform_is_zero(tmp_path):
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    assert "transform = 0" in conf


def test_write_hardware_conf_no_legacy_touch_output_key(tmp_path):
    """The old 'touch_output' key must never appear — it is not a valid Hyprland option."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    assert "touch_output" not in conf


# touch-panel-launcher + touch-panel-watch emission
# ---------------------------------------------------------------------------

def test_write_hardware_conf_emits_launcher_when_touch_detected(tmp_path):
    """touch-panel-launcher must be in exec-once when touchscreen is present."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    assert "exec-once = touch-panel-launcher" in conf


def test_write_hardware_conf_emits_watch_when_touch_detected(tmp_path):
    """touch-panel-watch must be in exec-once when touchscreen is present."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    assert "exec-once = touch-panel-watch" in conf


def test_write_hardware_conf_no_launcher_without_touchscreen(tmp_path):
    """touch-panel-launcher must NOT appear when there is no touchscreen."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=False)
    assert "touch-panel-launcher" not in conf


def test_write_hardware_conf_no_watch_without_touchscreen(tmp_path):
    """touch-panel-watch must NOT appear when there is no touchscreen."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=False)
    assert "touch-panel-watch" not in conf


def test_write_hardware_conf_no_legacy_touch_panel_exec(tmp_path):
    """The old 'exec-once = touch-panel' line must never be emitted."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=True)
    # 'touch-panel-launcher' and 'touch-panel-watch' contain 'touch-panel' as a
    # substring, so filter those out and ensure bare 'touch-panel' is absent.
    lines = [ln.strip() for ln in conf.splitlines()]
    assert "exec-once = touch-panel" not in lines


# ---------------------------------------------------------------------------
# write_hardware_conf() — Nvidia GPU env var generation
# ---------------------------------------------------------------------------

def test_write_hardware_conf_emits_libva_driver_when_nvidia(tmp_path):
    """LIBVA_DRIVER_NAME=nvidia must be set when Nvidia GPU is detected."""
    conf = _run_write_hardware_conf(tmp_path, has_nvidia=True)
    assert "env = LIBVA_DRIVER_NAME,nvidia" in conf


def test_write_hardware_conf_emits_glx_vendor_when_nvidia(tmp_path):
    """__GLX_VENDOR_LIBRARY_NAME=nvidia must be set when Nvidia GPU is detected."""
    conf = _run_write_hardware_conf(tmp_path, has_nvidia=True)
    assert "env = __GLX_VENDOR_LIBRARY_NAME,nvidia" in conf


def test_write_hardware_conf_no_libva_driver_without_nvidia(tmp_path):
    """LIBVA_DRIVER_NAME must NOT appear when no Nvidia GPU is present."""
    conf = _run_write_hardware_conf(tmp_path, has_nvidia=False)
    assert "LIBVA_DRIVER_NAME" not in conf


def test_write_hardware_conf_no_glx_vendor_without_nvidia(tmp_path):
    """__GLX_VENDOR_LIBRARY_NAME must NOT appear when no Nvidia GPU is present."""
    conf = _run_write_hardware_conf(tmp_path, has_nvidia=False)
    assert "__GLX_VENDOR_LIBRARY_NAME" not in conf


def test_write_hardware_conf_nvidia_with_touch(tmp_path):
    """Nvidia env vars and touchdevice block must both appear when both present."""
    conf = _run_write_hardware_conf(tmp_path, has_nvidia=True, has_touch=True)
    assert "env = LIBVA_DRIVER_NAME,nvidia" in conf
    assert "touchdevice" in conf


# touch-panel-launcher script behaviour
# ---------------------------------------------------------------------------

LAUNCHER = Path(__file__).parents[2] / "stow" / "hypr" / ".local" / "bin" / "touch-panel-launcher"


def _run_launcher(tmp_path: Path, *, has_kbd: bool) -> subprocess.CompletedProcess:
    """
    Run touch-panel-launcher with fake sysfs uevent files under tmp_path.
    If has_kbd=True, creates a uevent with ID_INPUT_KEYBOARD=1 and PHYS=usb-0000:00:14.0-2.
    The '/sys/class/input' path in the script is patched to tmp_path/sys/class/input.
    'exec touch-panel' is replaced with 'echo EXEC_TOUCH_PANEL' to observe execution.
    """
    fake_sys = tmp_path / "sys" / "class" / "input"
    if has_kbd:
        uevent_dir = fake_sys / "event0" / "device"
        uevent_dir.mkdir(parents=True)
        (uevent_dir / "uevent").write_text(
            "ID_INPUT_KEYBOARD=1\nPHYS=usb-0000:00:14.0-2\n"
        )
    else:
        # Create an input device that is NOT a keyboard (mouse)
        uevent_dir = fake_sys / "event0" / "device"
        uevent_dir.mkdir(parents=True)
        (uevent_dir / "uevent").write_text("ID_INPUT_MOUSE=1\n")

    source = LAUNCHER.read_text()
    patched = (
        source
        .replace("/sys/class/input", str(fake_sys))
        .replace("exec touch-panel", "echo EXEC_TOUCH_PANEL")
    )
    return subprocess.run(["bash", "-c", patched], capture_output=True, text=True)


def test_launcher_exits_silently_when_keyboard_present(tmp_path):
    """With a keyboard attached, the launcher should exit 0 and emit nothing."""
    result = _run_launcher(tmp_path, has_kbd=True)
    assert result.returncode == 0
    assert "EXEC_TOUCH_PANEL" not in result.stdout


def test_launcher_starts_panel_when_no_keyboard(tmp_path):
    """Without a keyboard, the launcher should exec touch-panel."""
    result = _run_launcher(tmp_path, has_kbd=False)
    assert result.returncode == 0
    assert "EXEC_TOUCH_PANEL" in result.stdout



# _hex_to_rgba — touch-panel CSS helper
# ---------------------------------------------------------------------------

TOUCH_PANEL = Path(__file__).parents[2] / "stow" / "hypr" / ".local" / "bin" / "touch-panel"


def _run_hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Extract and run _hex_to_rgba from touch-panel without importing gi."""
    source = TOUCH_PANEL.read_text()
    # Extract just the _hex_to_rgba function
    start = source.index("def _hex_to_rgba(")
    end   = source.index("\ndef ", start + 1)
    func  = source[start:end]
    script = f"{func}\nprint(_hex_to_rgba({hex_color!r}, {alpha}))"
    result = subprocess.run(["python3", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_hex_to_rgba_produces_rgba_not_hex():
    assert _run_hex_to_rgba("#1e1e2e", 0.93).startswith("rgba(")


def test_hex_to_rgba_correct_channels():
    out = _run_hex_to_rgba("#1e1e2e", 0.93)
    assert "30, 30, 46" in out  # 0x1e=30, 0x1e=30, 0x2e=46


def test_hex_to_rgba_alpha_preserved():
    out = _run_hex_to_rgba("#ffffff", 0.5)
    assert "0.5" in out


def test_hex_to_rgba_fallback_invalid():
    """Non-standard input is returned unchanged rather than crashing."""
    out = _run_hex_to_rgba("transparent", 0.9)
    assert out == "transparent"


# ---------------------------------------------------------------------------
# reapply_current_theme
# ---------------------------------------------------------------------------

def _run_reapply_current_theme(
    tmp_path: Path,
    *,
    state_content: str | None = None,   # None → no state file
    script_present: bool = True,
    python_exit_code: int = 0,
) -> tuple[int, str, str]:
    """
    Run reapply_current_theme() from setup.sh with a mocked home dir.
    Returns (returncode, stdout, stderr).
    """
    source = SETUP_SH.read_text()

    start = source.find("reapply_current_theme()")
    assert start != -1, "reapply_current_theme() not found in setup.sh"
    end = source.find("\n}", start)
    func = source[source.rfind("\n", 0, start) + 1: end + 2]

    # Set up fake home
    config_hypr = tmp_path / ".config" / "hypr"
    config_hypr.mkdir(parents=True)

    theme_dir = config_hypr / "scripts" / "theme-switcher"
    theme_dir.mkdir(parents=True)

    script_path = theme_dir / "switch_theme.py"
    if script_present:
        script_path.write_text(f"import sys; sys.exit({python_exit_code})\n")

    if state_content is not None:
        (config_hypr / ".current-theme").write_text(state_content)

    # Stub python3 to capture the args it was called with
    fake_python = tmp_path / "fake_python3"
    fake_python.write_text(
        f"#!/usr/bin/env bash\necho \"called: $@\"\nexit {python_exit_code}\n"
    )
    fake_python.chmod(0o755)

    bash_script = f"""
set -euo pipefail
HOME="{tmp_path}"
log_step() {{ echo "STEP: $1"; }}
log_ok()   {{ echo "OK: $1"; }}
log_warn() {{ echo "WARN: $1"; }}
{func.replace("python3", str(fake_python))}
reapply_current_theme
"""
    result = subprocess.run(["bash", "-c", bash_script], capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def test_reapply_current_theme_uses_state_file_when_present(tmp_path):
    rc, out, _ = _run_reapply_current_theme(tmp_path, state_content="catppuccin-frappe\n")
    assert rc == 0
    assert "catppuccin-frappe" in out
    assert "--no-reload" in out


def test_reapply_current_theme_defaults_to_catppuccin_mocha_when_no_state(tmp_path):
    rc, out, _ = _run_reapply_current_theme(tmp_path, state_content=None)
    assert rc == 0
    assert "catppuccin-mocha" in out
    assert "--no-reload" in out


def test_reapply_current_theme_warns_and_returns_when_script_missing(tmp_path):
    rc, out, _ = _run_reapply_current_theme(tmp_path, script_present=False)
    assert rc == 0
    assert "WARN" in out


def test_reapply_current_theme_warns_on_script_failure(tmp_path):
    rc, out, _ = _run_reapply_current_theme(
        tmp_path, state_content="catppuccin-mocha\n", python_exit_code=1
    )
    assert rc == 0           # reapply_current_theme itself must not fail
    assert "WARN" in out
