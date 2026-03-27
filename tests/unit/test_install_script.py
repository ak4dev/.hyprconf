"""
Unit tests for install.sh — ESP auto-creation, arrow_select, timezone picker,
network config copy, and wifi post-install guidance.

All tests are static-analysis only (no live disk, no TTY required).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
INSTALL_SH = REPO_ROOT / "install" / "install.sh"


def _text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def _extract_function(name: str) -> str:
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\)/,/^\\}}$/", str(INSTALL_SH)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _run_bash(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, env=full_env,
    )


# ---------------------------------------------------------------------------
# install.sh exists and is a valid bash script
# ---------------------------------------------------------------------------

def test_install_sh_exists() -> None:
    assert INSTALL_SH.exists(), "install/install.sh not found"


def test_install_sh_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALL_SH)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


# ---------------------------------------------------------------------------
# ESP auto-creation: < 1 GiB → no prompt
# ---------------------------------------------------------------------------

class TestEspAutoCreate:
    def test_size_check_present(self) -> None:
        """Script checks ESP total size in bytes with lsblk -bno SIZE."""
        text = _text()
        assert "esp_size_bytes" in text
        assert "lsblk -bno SIZE" in text

    def test_auto_create_threshold_is_1_gib(self) -> None:
        """Auto-create trigger is exactly 1 GiB (1024³ bytes)."""
        text = _text()
        assert "esp_size_bytes < 1024 * 1024 * 1024" in text

    def test_auto_create_message(self) -> None:
        """User-facing warning mentions '< 1 GiB' when auto-creating."""
        text = _text()
        assert "< 1 GiB" in text

    def test_choice_prompt_only_for_large_esp(self) -> None:
        """The [1]/[2] choice prompt is inside the else branch (large ESP only)."""
        func = _extract_function("partition_unallocated")
        # Both the size check and the choice prompt must be present.
        assert "esp_size_bytes < 1024 * 1024 * 1024" in func
        assert "How should we handle EFI" in func
        # The choice prompt must come AFTER the else keyword for the size check.
        size_pos = func.index("esp_size_bytes < 1024")
        choice_pos = func.index("How should we handle EFI")
        assert choice_pos > size_pos, (
            "'How should we handle EFI' must appear after the size check"
        )


# ---------------------------------------------------------------------------
# arrow_select: /dev/tty input, first-render flag, escape timeout
# ---------------------------------------------------------------------------

class TestArrowSelect:
    def test_reads_from_dev_tty(self) -> None:
        """arrow_select opens /dev/tty for keyboard input (fd 8), not stdin."""
        func = _extract_function("arrow_select")
        assert "exec 8</dev/tty" in func, (
            "arrow_select must open /dev/tty for reading on fd 8"
        )

    def test_read_uses_fd8(self) -> None:
        """All interactive read calls in arrow_select use -u8."""
        func = _extract_function("arrow_select")
        assert "read -rsn1 -u8 key" in func
        assert "read -rsn2 -t" in func and "-u8" in func

    def test_escape_sequence_has_timeout(self) -> None:
        """Escape sequence second read has a timeout to prevent hanging on bare ESC."""
        func = _extract_function("arrow_select")
        assert "-t0.15" in func or "-t 0.15" in func, (
            "Second read for escape sequence must have a timeout (-t0.15)"
        )

    def test_first_render_flag(self) -> None:
        """arrow_select skips cursor-up on the first render to avoid display glitches."""
        func = _extract_function("arrow_select")
        assert "first=1" in func or "first=0" in func, (
            "arrow_select must use a 'first' flag to skip cursor-up on initial render"
        )

    def test_does_not_check_stdin_tty(self) -> None:
        """arrow_select no longer requires stdin to be a TTY (uses /dev/tty directly)."""
        func = _extract_function("arrow_select")
        assert "[[ -t 0 ]]" not in func, (
            "arrow_select must not gate on stdin being a TTY"
        )

    def test_returns_nonzero_when_no_tty(self) -> None:
        """arrow_select returns 1 gracefully when /dev/tty cannot be opened."""
        result = _run_bash(
            "source /dev/stdin <<'EOF'\n"
            + INSTALL_SH.read_text() + "\n"
            "EOF\n"
            # Redirect /dev/tty to /dev/null so open fails, then call arrow_select
            "arrow_select 'test' a b c 9>/dev/null 2>/dev/null; echo exit:$?",
        )
        # Should fail gracefully (exit code 1), not crash/hang.
        assert "exit:1" in result.stdout or result.returncode != 0


# ---------------------------------------------------------------------------
# _ensure_fzf: exists, installs via pacman if missing
# ---------------------------------------------------------------------------

class TestEnsureFzf:
    def test_function_exists(self) -> None:
        assert "_ensure_fzf()" in _text()

    def test_uses_pacman(self) -> None:
        func = _extract_function("_ensure_fzf")
        assert "pacman" in func

    def test_noop_when_fzf_present(self) -> None:
        """_ensure_fzf exits 0 immediately if fzf is already on PATH."""
        func = _extract_function("_ensure_fzf")
        # Must have an early return when fzf is found.
        assert "command -v fzf" in func
        assert "return 0" in func

    def test_called_from_pick_timezone(self) -> None:
        """_pick_timezone calls _ensure_fzf before the fzf check."""
        func = _extract_function("_pick_timezone")
        assert "_ensure_fzf" in func, (
            "_pick_timezone must call _ensure_fzf to install fzf when missing"
        )
        # _ensure_fzf call must come before the fzf pipe.
        ensure_pos = func.index("_ensure_fzf")
        fzf_pos = func.index("fzf \\")
        assert ensure_pos < fzf_pos, (
            "_ensure_fzf must be called before the fzf pipe in _pick_timezone"
        )


# ---------------------------------------------------------------------------
# _pick_timezone: fzf invoked with /dev/tty I/O
# ---------------------------------------------------------------------------

class TestPickTimezone:
    def test_fzf_uses_dev_tty_io(self) -> None:
        """fzf in _pick_timezone uses </dev/tty >/dev/tty for correct terminal I/O."""
        func = _extract_function("_pick_timezone")
        assert "</dev/tty" in func and ">/dev/tty" in func, (
            "fzf call in _pick_timezone must redirect I/O through /dev/tty "
            "so it works correctly when stdout is captured in a subshell"
        )

    def test_no_tty_stdin_stdout_guard_on_fzf(self) -> None:
        """fzf branch no longer requires [[ -t 0 && -t 1 ]] since I/O is via /dev/tty."""
        func = _extract_function("_pick_timezone")
        # The old guard was: command -v fzf &>/dev/null && [[ -t 0 && -t 1 ]]
        assert "-t 0 && -t 1" not in func and "-t 0 &&" not in func, (
            "_pick_timezone fzf branch must not gate on stdin/stdout being TTYs"
        )

    def test_plain_text_fallback_present(self) -> None:
        """Plain-text read fallback remains as a last resort."""
        func = _extract_function("_pick_timezone")
        assert "Europe/London" in func or "read -r TIMEZONE" in func


# ---------------------------------------------------------------------------
# binary_install: scripts are symlinked alongside the binary
# ---------------------------------------------------------------------------

class TestBinaryInstallScripts:
    def test_hyprconf_tui_is_linked(self) -> None:
        """binary_install must link hyprconf-tui script directory."""
        func = _extract_function("binary_install")
        assert "hyprconf-tui" in func, (
            "binary_install must link the hyprconf-tui script directory"
        )

    def test_theme_switcher_is_linked(self) -> None:
        """binary_install must link theme-switcher directory."""
        func = _extract_function("binary_install")
        assert "theme-switcher" in func, (
            "binary_install must link the theme-switcher script directory"
        )

    def test_switch_monitor_sh_is_linked(self) -> None:
        """binary_install must link switch_monitor.sh."""
        func = _extract_function("binary_install")
        assert "switch_monitor.sh" in func, (
            "binary_install must link switch_monitor.sh"
        )

    def test_toggle_native_display_is_linked(self) -> None:
        """binary_install must link toggle-native-display."""
        func = _extract_function("binary_install")
        assert "toggle-native-display" in func, (
            "binary_install must link toggle-native-display"
        )

    def test_scripts_destination_dir_created(self) -> None:
        """binary_install must create the scripts destination directory."""
        func = _extract_function("binary_install")
        assert ".config/hypr/scripts" in func, (
            "binary_install must ensure ~/.config/hypr/scripts/ exists"
        )

    def test_no_sync_reference_in_tui_error(self) -> None:
        """cmd_tui error message must NOT tell users to run 'hyprconf sync'."""
        func = _extract_function("cmd_tui")
        assert "hyprconf sync" not in func, (
            "cmd_tui error message should not reference 'hyprconf sync' "
            "since binary-install users have no dotfiles to sync"
        )


# ---------------------------------------------------------------------------
# Network config copy and wifi guidance
# ---------------------------------------------------------------------------

class TestNetworkConfig:
    def test_iwd_in_pacstrap(self) -> None:
        """iwd must be in the pacstrap package list so wifi works out of the box."""
        text = _text()
        # The package list is declared as `local pkgs=(...)` then passed to pacstrap
        pkg_list_lines = [l for l in text.splitlines() if "local pkgs=(" in l and "networkmanager" in l]
        assert pkg_list_lines, "No pacstrap package list (local pkgs=...) found in install.sh"
        assert any("iwd" in l for l in pkg_list_lines), (
            "iwd must be in the pacstrap packages — without it or wpa_supplicant, "
            "NetworkManager cannot manage wifi"
        )

    def test_iwd_service_enabled_in_chroot(self) -> None:
        """iwd.service must be enabled inside the chroot so it starts on first boot."""
        text = _text()
        assert "systemctl enable iwd" in text, (
            "iwd.service must be enabled in the chroot setup so it starts on first boot"
        )

    def test_nm_wifi_backend_conf_written_in_chroot(self) -> None:
        """Chroot setup must write the NM wifi-backend.conf to use iwd."""
        text = _text()
        assert "wifi.backend=iwd" in text, (
            "install.sh must write /etc/NetworkManager/conf.d/wifi-backend.conf "
            "with wifi.backend=iwd in the chroot"
        )

    def test_no_wifi_profiles_warning_mentions_nmtui(self) -> None:
        """When no profiles are found, the warning must direct users to nmtui."""
        func = _extract_function("copy_network_config_from_iso")
        assert "nmtui" in func, (
            "copy_network_config_from_iso must mention 'nmtui' in its no-profiles "
            "warning so users know how to configure wifi after an ethernet install"
        )

    def test_copy_network_prefers_nm_profiles(self) -> None:
        """NM profiles must be preferred over iwd profiles when both might exist."""
        func = _extract_function("copy_network_config_from_iso")
        nm_pos = func.find("/etc/NetworkManager/system-connections")
        iwd_pos = func.find("/var/lib/iwd")
        assert nm_pos != -1, "Function must check for NM profiles"
        assert iwd_pos != -1, "Function must check for iwd profiles"
        assert nm_pos < iwd_pos, (
            "NM profile copy must be attempted before iwd profile import"
        )
