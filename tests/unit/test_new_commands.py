"""
Tests for new CLI commands: doctor, clipboard, screenshot, gamemode, power,
nightlight, autologin, colorpicker, record, theme generate.

Validates that each command function exists in the hyprconf binary,
has correct dispatcher entries, and appears in help text.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"


def _bin_text() -> str:
    return HYPRCONF_BIN.read_text()


# ---------------------------------------------------------------------------
# 1. cmd_doctor
# ---------------------------------------------------------------------------


class TestCmdDoctor:
    """Verify hyprconf doctor command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_doctor()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines() if "doctor)" in l and "cmd_doctor" in l]
        assert lines, "doctor must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf doctor" in _bin_text()

    def test_checks_packages(self) -> None:
        text = _bin_text()
        assert "_doctor_check_packages" in text

    def test_checks_services(self) -> None:
        text = _bin_text()
        assert "_doctor_check_services" in text

    def test_checks_configs(self) -> None:
        text = _bin_text()
        assert "_doctor_check_configs" in text

    def test_checks_symlinks(self) -> None:
        text = _bin_text()
        assert "_doctor_check_symlinks" in text

    def test_checks_theme(self) -> None:
        text = _bin_text()
        assert "_doctor_check_theme" in text

    def test_checks_hardware(self) -> None:
        text = _bin_text()
        assert "_doctor_check_hardware" in text

    def test_checks_shell(self) -> None:
        text = _bin_text()
        assert "_doctor_check_shell" in text

    def test_returns_nonzero_on_errors(self) -> None:
        """cmd_doctor must return 1 when errors are found."""
        text = _bin_text()
        idx = text.index("cmd_doctor()")
        body = text[idx : idx + 800]
        assert "return 1" in body

    def test_checks_nm_wifi_backend(self) -> None:
        """Doctor must verify NetworkManager wifi backend = iwd."""
        text = _bin_text()
        assert "wifi.backend=iwd" in text


# ---------------------------------------------------------------------------
# 2. cmd_clipboard
# ---------------------------------------------------------------------------


class TestCmdClipboard:
    """Verify hyprconf clipboard command."""

    def test_function_exists(self) -> None:
        assert "cmd_clipboard()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines() if "clipboard" in l and "cmd_clipboard" in l]
        assert lines, "clipboard must have a dispatcher entry"

    def test_clip_alias(self) -> None:
        """'clip' must be an alias for clipboard."""
        text = _bin_text()
        lines = [l for l in text.splitlines() if "clip)" in l and "cmd_clipboard" in l]
        assert lines, "'clip' alias must dispatch to cmd_clipboard"

    def test_supports_fzf_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_clipboard()")
        body = text[idx : idx + 500]
        assert "fzf" in body

    def test_supports_rofi_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_clipboard()")
        body = text[idx : idx + 500]
        assert "rofi" in body

    def test_supports_wipe(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_clipboard()")
        body = text[idx : idx + 500]
        assert "wipe" in body

    def test_uses_cliphist(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_clipboard()")
        body = text[idx : idx + 500]
        assert "cliphist" in body

    def test_help_text(self) -> None:
        assert "hyprconf clipboard" in _bin_text()


# ---------------------------------------------------------------------------
# 3. cmd_screenshot
# ---------------------------------------------------------------------------


class TestCmdScreenshot:
    """Verify hyprconf screenshot command."""

    def test_function_exists(self) -> None:
        assert "cmd_screenshot()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [
            l.strip() for l in text.splitlines() if "screenshot" in l and "cmd_screenshot" in l
        ]
        assert lines

    def test_ss_alias(self) -> None:
        """'ss' must be an alias for screenshot."""
        text = _bin_text()
        lines = [l for l in text.splitlines() if "ss)" in l and "cmd_screenshot" in l]
        assert lines, "'ss' alias must dispatch to cmd_screenshot"

    def test_region_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_screenshot()")
        body = text[idx : idx + 600]
        assert "region" in body

    def test_window_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_screenshot()")
        body = text[idx : idx + 600]
        assert "window" in body

    def test_full_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_screenshot()")
        body = text[idx : idx + 600]
        assert "full" in body

    def test_edit_mode_with_swappy(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_screenshot()")
        body = text[idx : idx + 800]
        assert "swappy" in body

    def test_uses_hyprshot(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_screenshot()")
        body = text[idx : idx + 600]
        assert "hyprshot" in body

    def test_help_text(self) -> None:
        assert "hyprconf screenshot" in _bin_text()


# ---------------------------------------------------------------------------
# 4. cmd_gamemode
# ---------------------------------------------------------------------------


class TestCmdGamemode:
    """Verify hyprconf gamemode command."""

    def test_function_exists(self) -> None:
        assert "cmd_gamemode()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines() if "gamemode" in l and "cmd_gamemode" in l]
        assert lines

    def test_game_alias(self) -> None:
        """'game' must be an alias for gamemode."""
        text = _bin_text()
        lines = [l for l in text.splitlines() if "game)" in l and "cmd_gamemode" in l]
        assert lines, "'game' alias must dispatch to cmd_gamemode"

    def test_on_off_toggle(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_gamemode()")
        body = text[idx : idx + 300]
        assert "on" in body
        assert "off" in body
        assert "toggle" in body

    def test_status_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_gamemode()")
        body = text[idx : idx + 500]
        assert "status" in body

    def test_disables_animations(self) -> None:
        text = _bin_text()
        assert "animations:enabled false" in text or "animations:enabled 0" in text

    def test_disables_blur(self) -> None:
        text = _bin_text()
        assert "blur:enabled false" in text or "blur:enabled 0" in text

    def test_disables_shadows(self) -> None:
        text = _bin_text()
        assert "shadow:enabled false" in text or "shadow:enabled 0" in text

    def test_restores_via_reload(self) -> None:
        """Game mode off must restore settings (via hyprctl reload)."""
        text = _bin_text()
        # Find _gamemode_off function
        idx = text.index("_gamemode_off()")
        body = text[idx : idx + 300]
        assert "hyprctl reload" in body

    def test_state_file(self) -> None:
        """Game mode must use a state file for toggle tracking."""
        text = _bin_text()
        assert "_GAMEMODE_STATE" in text

    def test_help_text(self) -> None:
        assert "hyprconf gamemode" in _bin_text()


# ---------------------------------------------------------------------------
# 5. cmd_power
# ---------------------------------------------------------------------------


class TestCmdPower:
    """Verify hyprconf power command."""

    def test_function_exists(self) -> None:
        assert "cmd_power()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines() if "power)" in l and "cmd_power" in l]
        assert lines

    def test_lock_action(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power()")
        body = text[idx : idx + 1000]
        assert "hyprlock" in body

    def test_logout_action(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power()")
        body = text[idx : idx + 1000]
        assert "dispatch exit" in body

    def test_suspend_action(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power()")
        body = text[idx : idx + 1000]
        assert "systemctl suspend" in body

    def test_reboot_action(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power()")
        body = text[idx : idx + 1000]
        assert "systemctl reboot" in body

    def test_shutdown_action(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power()")
        body = text[idx : idx + 1000]
        assert "systemctl poweroff" in body

    def test_interactive_menu(self) -> None:
        """Power with no args must show interactive picker."""
        text = _bin_text()
        idx = text.index("cmd_power()")
        body = text[idx : idx + 1000]
        assert "fzf" in body or "read -r" in body

    def test_help_text(self) -> None:
        assert "hyprconf power" in _bin_text()


# ---------------------------------------------------------------------------
# 6. cmd_nightlight
# ---------------------------------------------------------------------------


class TestCmdNightlight:
    """Verify hyprconf nightlight command."""

    def test_function_exists(self) -> None:
        assert "cmd_nightlight()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [
            l.strip() for l in text.splitlines() if "nightlight" in l and "cmd_nightlight" in l
        ]
        assert lines

    def test_night_alias(self) -> None:
        text = _bin_text()
        lines = [l for l in text.splitlines() if "night)" in l and "cmd_nightlight" in l]
        assert lines, "'night' alias must dispatch to cmd_nightlight"

    def test_on_off_toggle(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_nightlight()")
        body = text[idx : idx + 400]
        assert "on)" in body or "on\n" in body
        assert "off)" in body
        assert "toggle)" in body

    def test_status_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_nightlight()")
        body = text[idx : idx + 500]
        assert "status" in body

    def test_uses_hyprsunset(self) -> None:
        text = _bin_text()
        assert "hyprsunset" in text

    def test_pid_tracking(self) -> None:
        """Nightlight must use PID tracking (not pkill)."""
        text = _bin_text()
        assert "_NIGHTLIGHT_PID" in text
        assert "pkill" not in text, "Must use PID tracking, not pkill"

    def test_help_text(self) -> None:
        assert "hyprconf nightlight" in _bin_text()


# ---------------------------------------------------------------------------
# 7. cmd_colorpicker
# ---------------------------------------------------------------------------


class TestCmdColorpicker:
    """Verify hyprconf colorpicker command."""

    def test_function_exists(self) -> None:
        assert "cmd_colorpicker()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [
            l.strip() for l in text.splitlines() if "colorpicker" in l and "cmd_colorpicker" in l
        ]
        assert lines

    def test_color_alias(self) -> None:
        text = _bin_text()
        lines = [l for l in text.splitlines() if "color)" in l and "cmd_colorpicker" in l]
        assert lines, "'color' alias must dispatch to cmd_colorpicker"

    def test_hex_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_colorpicker()")
        body = text[idx : idx + 400]
        assert "hex" in body

    def test_rgb_mode(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_colorpicker()")
        body = text[idx : idx + 400]
        assert "rgb" in body

    def test_uses_hyprpicker(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_colorpicker()")
        body = text[idx : idx + 400]
        assert "hyprpicker" in body

    def test_help_text(self) -> None:
        assert "hyprconf colorpicker" in _bin_text()


# ---------------------------------------------------------------------------
# 8. cmd_record
# ---------------------------------------------------------------------------


class TestCmdRecord:
    """Verify hyprconf record command."""

    def test_function_exists(self) -> None:
        assert "cmd_record()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines() if "record" in l and "cmd_record" in l]
        assert lines

    def test_rec_alias(self) -> None:
        text = _bin_text()
        lines = [l for l in text.splitlines() if "rec)" in l and "cmd_record" in l]
        assert lines, "'rec' alias must dispatch to cmd_record"

    def test_start_stop_toggle(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_record()")
        body = text[idx : idx + 400]
        assert "start" in body
        assert "stop" in body
        assert "toggle" in body

    def test_status_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_record()")
        body = text[idx : idx + 500]
        assert "status" in body

    def test_pid_tracking(self) -> None:
        text = _bin_text()
        assert "_RECORD_PIDFILE" in text

    def test_uses_wf_recorder(self) -> None:
        text = _bin_text()
        assert "wf-recorder" in text

    def test_help_text(self) -> None:
        assert "hyprconf record" in _bin_text()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 9. theme generate
# ---------------------------------------------------------------------------


class TestThemeGenerate:
    """Verify hyprconf theme generate command."""

    def test_generate_in_binary(self) -> None:
        """cmd_theme must dispatch 'generate' subcommand."""
        text = _bin_text()
        idx = text.index("cmd_theme()")
        body = text[idx : idx + 800]
        assert "generate)" in body
        assert "--generate" in body

    def test_help_text(self) -> None:
        assert "theme generate" in _bin_text()

    def test_generate_function_in_switch_theme(self) -> None:
        """switch_theme.py must have generate_theme_from_wallpaper()."""
        theme_script = (
            REPO_ROOT
            / "stow"
            / "hypr"
            / ".config"
            / "hypr"
            / "scripts"
            / "theme-switcher"
            / "switch_theme.py"
        )
        text = theme_script.read_text()
        assert "def generate_theme_from_wallpaper" in text

    def test_generate_flag_in_argparse(self) -> None:
        """switch_theme.py must accept --generate flag."""
        theme_script = (
            REPO_ROOT
            / "stow"
            / "hypr"
            / ".config"
            / "hypr"
            / "scripts"
            / "theme-switcher"
            / "switch_theme.py"
        )
        text = theme_script.read_text()
        assert '"--generate"' in text

    def test_extracts_dominant_colors(self) -> None:
        """Generator must have colour extraction function."""
        theme_script = (
            REPO_ROOT
            / "stow"
            / "hypr"
            / ".config"
            / "hypr"
            / "scripts"
            / "theme-switcher"
            / "switch_theme.py"
        )
        text = theme_script.read_text()
        assert "_extract_dominant_colors" in text

    def test_generates_required_keys(self) -> None:
        """Generated theme must include all required JSON keys."""
        theme_script = (
            REPO_ROOT
            / "stow"
            / "hypr"
            / ".config"
            / "hypr"
            / "scripts"
            / "theme-switcher"
            / "switch_theme.py"
        )
        text = theme_script.read_text()
        idx = text.index("def generate_theme_from_wallpaper")
        body = text[idx : idx + 2000]
        for key in (
            "background",
            "foreground",
            "comment",
            "accent",
            "red",
            "orange",
            "green",
            "cyan",
        ):
            assert f'"{key}"' in body, f"Generated theme must include '{key}'"

    def test_saves_to_themes_dir(self) -> None:
        """Generated theme must be saved to themes directory."""
        theme_script = (
            REPO_ROOT
            / "stow"
            / "hypr"
            / ".config"
            / "hypr"
            / "scripts"
            / "theme-switcher"
            / "switch_theme.py"
        )
        text = theme_script.read_text()
        idx = text.index("def generate_theme_from_wallpaper")
        body = text[idx : idx + 3000]
        assert "THEMES_DIR" in body

    def test_pillow_in_packages(self) -> None:
        """python-pillow must be in the packages file."""
        pkgs = (REPO_ROOT / "packages").read_text()
        assert "python-pillow" in pkgs


# ---------------------------------------------------------------------------
# 10. cmd_autologin
# ---------------------------------------------------------------------------


class TestCmdAutologin:
    """Verify hyprconf autologin command (tty1 getty drop-in toggle)."""

    def test_function_exists(self) -> None:
        assert "cmd_autologin()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines() if "autologin)" in l and "cmd_autologin" in l]
        assert lines, "autologin must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf autologin" in _bin_text()

    def test_on_off_toggle_status(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_autologin()")
        body = text[idx : idx + 500]
        assert "on" in body
        assert "off" in body
        assert "toggle" in body
        assert "status" in body

    def test_defaults_to_status(self) -> None:
        """No argument must show status, never flip a security setting."""
        text = _bin_text()
        idx = text.index("cmd_autologin()")
        body = text[idx : idx + 200]
        assert '"${1:-status}"' in body

    def test_manages_getty_dropin(self) -> None:
        text = _bin_text()
        assert "getty@tty1.service.d" in text
        assert "--autologin" in text

    def test_daemon_reload_after_change(self) -> None:
        """Drop-in changes must be followed by a systemd daemon-reload."""
        text = _bin_text()
        idx = text.index("_autologin_on()")
        assert "systemctl daemon-reload" in text[idx : idx + 1200]
        idx = text.index("_autologin_off()")
        assert "systemctl daemon-reload" in text[idx : idx + 1200]

    def test_detects_foreign_dropins(self) -> None:
        """Any *.conf in the drop-in dir counts, not just the managed file."""
        text = _bin_text()
        idx = text.index("_autologin_active_file()")
        body = text[idx : idx + 400]
        assert '"$_AUTOLOGIN_DIR"/*.conf' in body

    def test_not_managed_by_setup(self) -> None:
        """setup.sh must not silently configure autologin on install."""
        setup = (REPO_ROOT / "setup.sh").read_text()
        assert "--autologin" not in setup
