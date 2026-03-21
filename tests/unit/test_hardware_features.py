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
# _has_physical_keyboard() — setup.sh helper
# ---------------------------------------------------------------------------

SETUP_SH = Path(__file__).parent.parent.parent / "setup.sh"


def _run_keyboard_detection(files: dict) -> bool:
    """Run _has_physical_keyboard() with a mocked /sys/class/input tree."""
    source = SETUP_SH.read_text()
    # Extract just the _has_physical_keyboard function
    start = source.find("_has_physical_keyboard()")
    assert start != -1, "_has_physical_keyboard() not found in setup.sh"
    # Extract until the closing brace
    end = source.find("\n}", start)
    func = source[source.rfind("\n", 0, start) + 1: end + 2]

    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        # Build fake sysfs tree
        for path, content in files.items():
            full = os.path.join(tmp, path.lstrip("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            Path(full).write_text(content)

        # Rewrite all /sys/class/input refs to use tmp dir
        func_patched = func.replace(
            "/sys/class/input/*/device/uevent",
            f"{tmp}/sys/class/input/*/device/uevent",
        )
        script = f"""
set -euo pipefail
{func_patched}
_has_physical_keyboard && echo YES || echo NO
"""
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True,
        )
        return result.stdout.strip() == "YES"


def test_physical_keyboard_detected_with_keyboard_and_phys():
    files = {
        "/sys/class/input/event1/device/uevent": (
            "NAME=\"AT Translated Set 2 keyboard\"\n"
            "ID_INPUT=1\nID_INPUT_KEYBOARD=1\n"
            "PHYS=\"isa0060/serio0/input0\"\n"
        )
    }
    assert _run_keyboard_detection(files) is True


def test_physical_keyboard_not_detected_when_phys_empty():
    """Power button / virtual keyboard: ID_INPUT_KEYBOARD=1 but PHYS is empty."""
    files = {
        "/sys/class/input/event2/device/uevent": (
            "NAME=\"Power Button\"\n"
            "ID_INPUT=1\nID_INPUT_KEYBOARD=1\n"
            "PHYS=\n"
        )
    }
    assert _run_keyboard_detection(files) is False


def test_physical_keyboard_not_detected_when_phys_missing():
    """No PHYS line at all — should not count as a physical keyboard."""
    files = {
        "/sys/class/input/event3/device/uevent": (
            "NAME=\"Virtual Keyboard\"\n"
            "ID_INPUT=1\nID_INPUT_KEYBOARD=1\n"
        )
    }
    assert _run_keyboard_detection(files) is False


def test_physical_keyboard_not_detected_when_absent():
    files = {
        "/sys/class/input/event0/device/uevent": (
            "NAME=\"ELAN Touchscreen\"\n"
            "ID_INPUT=1\nID_INPUT_TOUCHSCREEN=1\n"
        )
    }
    assert _run_keyboard_detection(files) is False


def test_keyboard_detected_among_multiple_devices():
    """Physical keyboard should be found even with other devices present."""
    files = {
        "/sys/class/input/event0/device/uevent": (
            "NAME=\"ELAN Touchscreen\"\nID_INPUT_TOUCHSCREEN=1\n"
        ),
        "/sys/class/input/event1/device/uevent": (
            "NAME=\"AT Translated Set 2 keyboard\"\n"
            "ID_INPUT_KEYBOARD=1\nPHYS=\"isa0060/serio0/input0\"\n"
        ),
    }
    assert _run_keyboard_detection(files) is True


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
# _get_touch_device_names() — setup.sh helper
# ---------------------------------------------------------------------------


def _run_touch_device_names(files: dict) -> list[str]:
    """Run _get_touch_device_names() with a mocked /sys/class/input tree."""
    source = SETUP_SH.read_text()
    start = source.find("_get_touch_device_names()")
    assert start != -1, "_get_touch_device_names() not found in setup.sh"
    end = source.find("\n}", start)
    func = source[source.rfind("\n", 0, start) + 1: end + 2]

    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp:
        for path, content in files.items():
            full = os.path.join(tmp, path.lstrip("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            Path(full).write_text(content)

        func_patched = func.replace(
            "/sys/class/input/*/device/uevent",
            f"{tmp}/sys/class/input/*/device/uevent",
        )
        script = f"""
set -euo pipefail
{func_patched}
_get_touch_device_names
"""
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True,
        )
        return [line for line in result.stdout.splitlines() if line]


def test_get_touch_device_names_standard_touchscreen():
    """ELAN HID touchscreen: name normalised to lowercase-hyphenated."""
    files = {
        "/sys/class/input/event0/device/uevent": (
            'NAME="ELAN Touchscreen"\nPHYS="i2c-ELAN0001:00"\n'
            "ID_INPUT_TOUCHSCREEN=1\n"
        )
    }
    assert _run_touch_device_names(files) == ["elan-touchscreen"]


def test_get_touch_device_names_wacom_i2c_finger():
    """ThinkPad X13 Yoga Wacom Finger node normalised correctly."""
    files = {
        "/sys/class/input/event9/device/uevent": (
            'NAME="Wacom HID 5288 Finger"\n'
            'PHYS="i2c-WACF2200:00"\n'
            "ABS=260800000000003\n"
        )
    }
    assert _run_touch_device_names(files) == ["wacom-hid-5288-finger"]


def test_get_touch_device_names_ignores_pen_node():
    """Pen event node must not appear — only the Finger node qualifies."""
    files = {
        "/sys/class/input/event8/device/uevent": (
            'NAME="Wacom HID 5288 Pen"\n'
            'PHYS="i2c-WACF2200:00"\n'
        )
    }
    assert _run_touch_device_names(files) == []


def test_get_touch_device_names_ignores_usb_wacom_tablet():
    """External USB Wacom Finger node must not appear (PHYS is usb-, not i2c-)."""
    files = {
        "/sys/class/input/event3/device/uevent": (
            'NAME="Wacom Intuos Pro M Finger"\n'
            'PHYS="usb-0000:00:14.0-3/input1"\n'
        )
    }
    assert _run_touch_device_names(files) == []


def test_get_touch_device_names_deduplicates_same_device():
    """Multiple event nodes with the same normalised name collapse to one entry."""
    files = {
        "/sys/class/input/event0/device/uevent": (
            'NAME="ELAN Touchscreen"\nID_INPUT_TOUCHSCREEN=1\n'
        ),
        "/sys/class/input/event1/device/uevent": (
            'NAME="ELAN Touchscreen"\nID_INPUT_TOUCHSCREEN=1\n'
        ),
    }
    names = _run_touch_device_names(files)
    assert names.count("elan-touchscreen") == 1


def test_get_touch_device_names_multiple_devices():
    """Two distinct touchscreen devices each appear once."""
    files = {
        "/sys/class/input/event0/device/uevent": (
            'NAME="ELAN Touchscreen"\nID_INPUT_TOUCHSCREEN=1\n'
        ),
        "/sys/class/input/event1/device/uevent": (
            'NAME="Wacom HID 48D3 Finger"\n'
            'PHYS="i2c-WACF2200:00"\n'
        ),
    }
    names = _run_touch_device_names(files)
    assert "elan-touchscreen" in names
    assert "wacom-hid-48d3-finger" in names
    assert len(names) == 2


def test_get_touch_device_names_empty_when_no_touch():
    files = {
        "/sys/class/input/event0/device/uevent": (
            'NAME="AT Translated Set 2 keyboard"\n'
            "ID_INPUT_KEYBOARD=1\nPHYS=\"isa0060\"\n"
        )
    }
    assert _run_touch_device_names(files) == []


# ---------------------------------------------------------------------------
# write_hardware_conf() — device block generation
# ---------------------------------------------------------------------------

def _run_write_hardware_conf(
    tmp_path: Path,
    *,
    has_touch: bool = False,
    touch_names: list[str] | None = None,
    has_accel: bool = False,
) -> str:
    """
    Run write_hardware_conf() (extracted from setup.sh) with stubbed helpers.
    Returns the text of the generated 60-hardware.conf.
    """
    touch_names = touch_names or []
    source = SETUP_SH.read_text()

    # Extract write_hardware_conf and its inner helper _get_touch_device_names
    def _extract_func(source: str, name: str) -> str:
        start = source.find(f"{name}()")
        assert start != -1, f"{name}() not found in setup.sh"
        end = source.find("\n}", start)
        return source[source.rfind("\n", 0, start) + 1: end + 2]

    write_func = _extract_func(source, "write_hardware_conf")
    get_names_func = _extract_func(source, "_get_touch_device_names")

    conf_dir = tmp_path / ".config" / "hypr" / "conf.d"
    conf_dir.mkdir(parents=True)

    if touch_names:
        names_printf = " ".join(f'"{n}"' for n in touch_names)
        get_names_stub = f'_get_touch_device_names() {{ printf "%s\\n" {names_printf}; }}'
    else:
        get_names_stub = "_get_touch_device_names() { return 0; }"

    script = f"""
set -euo pipefail
HOME="{tmp_path}"
_has_touchscreen()       {{ {'return 0' if has_touch else 'return 1'}; }}
_has_accelerometer()     {{ {'return 0' if has_accel  else 'return 1'}; }}
{get_names_stub}
log_ok() {{ :; }}
{write_func}
write_hardware_conf
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, f"write_hardware_conf failed:\n{result.stderr}"
    return (conf_dir / "60-hardware.conf").read_text()


def test_write_hardware_conf_no_device_block_without_touchscreen(tmp_path):
    conf = _run_write_hardware_conf(tmp_path, has_touch=False)
    assert "device {" not in conf


def test_write_hardware_conf_device_block_present_with_touchscreen(tmp_path):
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["wacom-hid-5288-finger"]
    )
    assert "device {" in conf


def test_write_hardware_conf_device_block_has_correct_name(tmp_path):
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["wacom-hid-5288-finger"]
    )
    assert "name         = wacom-hid-5288-finger" in conf


def test_write_hardware_conf_device_block_has_touch_output(tmp_path):
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["elan-touchscreen"]
    )
    assert "touch_output = eDP-1" in conf


def test_write_hardware_conf_device_block_has_transform_zero(tmp_path):
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["elan-touchscreen"]
    )
    assert "transform    = 0" in conf


def test_write_hardware_conf_multiple_touch_devices_emit_multiple_blocks(tmp_path):
    conf = _run_write_hardware_conf(
        tmp_path,
        has_touch=True,
        touch_names=["elan-touchscreen", "wacom-hid-5288-finger"],
    )
    assert conf.count("device {") == 2
    assert "name         = elan-touchscreen" in conf
    assert "name         = wacom-hid-5288-finger" in conf


def test_write_hardware_conf_no_device_block_when_no_touch_names(tmp_path):
    """Touchscreen detected but name list empty — no device blocks emitted."""
    conf = _run_write_hardware_conf(tmp_path, has_touch=True, touch_names=[])
    assert "device {" not in conf


# touch-panel-launcher + touch-panel-watch emission
# ---------------------------------------------------------------------------

def test_write_hardware_conf_emits_launcher_when_touch_detected(tmp_path):
    """touch-panel-launcher must be in exec-once when touchscreen is present."""
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["elan-touchscreen"]
    )
    assert "exec-once = touch-panel-launcher" in conf


def test_write_hardware_conf_emits_watch_when_touch_detected(tmp_path):
    """touch-panel-watch must be in exec-once when touchscreen is present."""
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["elan-touchscreen"]
    )
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
    conf = _run_write_hardware_conf(
        tmp_path, has_touch=True, touch_names=["elan-touchscreen"]
    )
    # 'touch-panel-launcher' and 'touch-panel-watch' contain 'touch-panel' as a
    # substring, so filter those out and ensure bare 'touch-panel' is absent.
    lines = [ln.strip() for ln in conf.splitlines()]
    assert "exec-once = touch-panel" not in lines


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

