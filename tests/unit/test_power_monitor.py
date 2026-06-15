"""Tests for hyprconf-power-monitor script and hyprconf power-profile CLI command."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"
POWER_MONITOR = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf-power-monitor"
SETUP_SH = REPO_ROOT / "setup.sh"


def _bin_text() -> str:
    return HYPRCONF_BIN.read_text()


def _setup_text() -> str:
    return SETUP_SH.read_text()


# ===========================================================================
# hyprconf-power-monitor script tests
# ===========================================================================


def _build_sysfs(tmp: Path, *, ac_online: int = 1, has_battery: bool = True) -> Path:
    """Create a fake sysfs tree for power_supply testing."""
    sysfs = tmp / "sys" / "class" / "power_supply"
    sysfs.mkdir(parents=True, exist_ok=True)

    if has_battery:
        bat = sysfs / "BAT0"
        bat.mkdir(exist_ok=True)
        (bat / "type").write_text("Battery")

    ac = sysfs / "AC0"
    ac.mkdir(exist_ok=True)
    (ac / "type").write_text("Mains")
    (ac / "online").write_text(str(ac_online))

    return sysfs


def _run_monitor(
    tmp: Path,
    *,
    ac_online: int = 1,
    has_battery: bool = True,
    args: list[str] | None = None,
    has_powerprofilesctl: bool = True,
) -> tuple[int, str, str, list[str]]:
    """Run hyprconf-power-monitor with faked sysfs and powerprofilesctl.

    Returns (rc, stdout, stderr, powerprofilesctl_calls).
    """
    fake_dir = tmp / "fakebin"
    fake_dir.mkdir(exist_ok=True)
    calls_file = tmp / "pp_calls.txt"

    if has_powerprofilesctl:
        fake_pp = fake_dir / "powerprofilesctl"
        fake_pp.write_text(
            f"""#!/usr/bin/env bash
if [[ "$1" == "get" ]]; then
    if [[ -f "{tmp}/current_profile" ]]; then
        cat "{tmp}/current_profile"
    else
        echo "balanced"
    fi
elif [[ "$1" == "set" ]]; then
    echo "$2" > "{tmp}/current_profile"
    echo "set $2" >> "{calls_file}"
fi
"""
        )
        fake_pp.chmod(0o755)

    fake_logger = fake_dir / "logger"
    fake_logger.write_text("#!/usr/bin/env bash\n# no-op\n")
    fake_logger.chmod(0o755)

    sysfs = _build_sysfs(tmp, ac_online=ac_online, has_battery=has_battery)

    # Rewrite the script to use our fake sysfs paths
    script_text = POWER_MONITOR.read_text()
    patched = script_text.replace(
        "/sys/class/power_supply/BAT*",
        str(sysfs / "BAT*"),
    ).replace(
        "/sys/class/power_supply/*/type",
        str(sysfs / "*/type"),
    )
    patched_script = tmp / "hyprconf-power-monitor"
    patched_script.write_text(patched)
    patched_script.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_dir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(patched_script)] + (args or []),
        env=env,
        capture_output=True,
        text=True,
    )

    calls: list[str] = []
    if calls_file.exists():
        calls = [ln.strip() for ln in calls_file.read_text().splitlines() if ln.strip()]

    return result.returncode, result.stdout, result.stderr, calls


class TestPowerMonitorAutoAC:
    """When AC is plugged in, should set performance."""

    def test_sets_performance_on_ac(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, ac_online=1)
        assert rc == 0
        assert "set performance" in calls

    def test_sets_power_saver_on_battery(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, ac_online=0)
        assert rc == 0
        assert "set power-saver" in calls


class TestPowerMonitorGuards:
    """Guard clauses: exits cleanly when prereqs missing."""

    def test_exits_if_no_powerprofilesctl(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, has_powerprofilesctl=False)
        assert rc == 0
        assert calls == []

    def test_exits_if_no_battery(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, has_battery=False)
        assert rc == 0
        assert calls == []


class TestPowerMonitorStatus:
    """Status subcommand should report profile and AC state."""

    def test_status_shows_profile(self, tmp_path: Path) -> None:
        rc, stdout, _, _ = _run_monitor(tmp_path, ac_online=1, args=["status"])
        assert rc == 0
        assert "Power profile:" in stdout

    def test_status_shows_ac_state_plugged(self, tmp_path: Path) -> None:
        rc, stdout, _, _ = _run_monitor(tmp_path, ac_online=1, args=["status"])
        assert "plugged in" in stdout

    def test_status_shows_ac_state_battery(self, tmp_path: Path) -> None:
        rc, stdout, _, _ = _run_monitor(tmp_path, ac_online=0, args=["status"])
        assert "on battery" in stdout


class TestPowerMonitorIdempotent:
    """Running twice with the same AC state should not fail."""

    def test_double_apply_ac(self, tmp_path: Path) -> None:
        # First run sets performance
        _run_monitor(tmp_path, ac_online=1)
        # Second run: profile already matches
        rc, _, _, calls = _run_monitor(tmp_path, ac_online=1)
        assert rc == 0

    def test_double_apply_battery(self, tmp_path: Path) -> None:
        _run_monitor(tmp_path, ac_online=0)
        rc, _, _, calls = _run_monitor(tmp_path, ac_online=0)
        assert rc == 0


class TestPowerMonitorInvalidArgs:
    """Invalid subcommand should fail gracefully."""

    def test_invalid_arg(self, tmp_path: Path) -> None:
        rc, _, stderr, _ = _run_monitor(tmp_path, args=["invalid"])
        assert rc != 0
        assert "Usage" in stderr


class TestPowerMonitorScriptExists:
    """Basic sanity: script file exists and is executable."""

    def test_file_exists(self) -> None:
        assert POWER_MONITOR.exists()

    def test_is_executable(self) -> None:
        assert os.access(POWER_MONITOR, os.X_OK)

    def test_shebang(self) -> None:
        first_line = POWER_MONITOR.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_strict_mode(self) -> None:
        text = POWER_MONITOR.read_text()
        assert "set -euo pipefail" in text


# ===========================================================================
# hyprconf power-profile CLI command tests (static analysis)
# ===========================================================================


class TestCmdPowerProfile:
    """Verify hyprconf power-profile command structure in the binary."""

    def test_function_exists(self) -> None:
        assert "cmd_power_profile()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [
            l.strip()
            for l in text.splitlines()
            if "power-profile" in l and "cmd_power_profile" in l
        ]
        assert lines, "power-profile must have a dispatcher entry in main()"

    def test_pp_alias(self) -> None:
        """pp shortcut must also dispatch to cmd_power_profile."""
        text = _bin_text()
        assert "pp)" in text

    def test_help_text(self) -> None:
        assert "hyprconf power-profile" in _bin_text()

    def test_status_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "status)" in body

    def test_performance_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "performance" in body

    def test_balanced_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "balanced" in body

    def test_power_saver_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "power-saver" in body

    def test_auto_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "auto)" in body

    def test_calls_powerprofilesctl(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "powerprofilesctl" in body

    def test_usage_on_invalid_arg(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_power_profile()")
        body = text[idx : idx + 2500]
        assert "Usage:" in body


# ===========================================================================
# Doctor checks for power profile (static analysis)
# ===========================================================================


class TestDoctorPowerProfile:
    """Verify doctor checks for power profile auto-switching."""

    def test_doctor_checks_udev_rule(self) -> None:
        text = _bin_text()
        assert "99-hyprconf-power.rules" in text

    def test_doctor_checks_power_monitor(self) -> None:
        text = _bin_text()
        assert "hyprconf-power-monitor" in text

    def test_doctor_battery_guard(self) -> None:
        """Doctor power-profile checks should be guarded by battery presence."""
        text = _bin_text()
        # The BAT* check should appear in the doctor section
        idx = text.index("_doctor_check_hardware()")
        body = text[idx : idx + 2000]
        assert "BAT" in body


# ===========================================================================
# setup.sh — power monitor setup function
# ===========================================================================


class TestSetupPowerMonitor:
    """Verify setup.sh has the power monitor installation logic."""

    def test_setup_power_monitor_function_exists(self) -> None:
        assert "setup_power_monitor()" in _setup_text()

    def test_udev_rule_path(self) -> None:
        text = _setup_text()
        assert "99-hyprconf-power.rules" in text

    def test_udev_rule_content(self) -> None:
        text = _setup_text()
        assert "SUBSYSTEM==" in text
        assert "power_supply" in text
        assert "ATTR{type}==" in text
        assert "Mains" in text

    def test_udev_rule_target_is_root_owned_not_home(self) -> None:
        """SECURITY: udev RUN+= runs as root, so the rule must NOT execute a
        user-writable $HOME path (that would be a local privilege escalation).
        The rule must point at the root-owned /usr/local/lib copy."""
        text = _setup_text()
        idx = text.index("setup_power_monitor()")
        body = text[idx : idx + 4000]
        # The RUN+= target must be the root-owned system path.
        assert 'RUN+=\\"$system_script\\"' in body
        assert "/usr/local/lib/hyprconf/hyprconf-power-monitor" in body
        # And the root-owned copy must be installed root:root.
        assert "install -Dm755 -o root -g root" in body
        # Defensive: the literal RUN+= line must never reference a home path.
        for line in body.splitlines():
            if "RUN+=" in line and "ACTION==" in line:
                assert "/home/" not in line and "$HOME" not in line

    def test_udevadm_reload(self) -> None:
        text = _setup_text()
        assert "udevadm control --reload-rules" in text

    def test_called_from_laptop_branch(self) -> None:
        """setup_power_monitor must be called when laptop is detected."""
        text = _setup_text()
        idx = text.index("Laptop/portable detected")
        block = text[idx : idx + 1500]
        assert "setup_power_monitor" in block

    def test_idempotent_check(self) -> None:
        """Should skip if rule already installed with correct content."""
        text = _setup_text()
        idx = text.index("setup_power_monitor()")
        body = text[idx : idx + 4000]
        assert "already installed" in body

    def test_initial_profile_set(self) -> None:
        """Should run the monitor once to set initial profile."""
        text = _setup_text()
        idx = text.index("setup_power_monitor()")
        body = text[idx : idx + 4000]
        assert "auto" in body
