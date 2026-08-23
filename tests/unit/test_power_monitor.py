"""Tests for the hyprconf-power-monitor script and its setup.sh installation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POWER_MONITOR = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf-power-monitor"
SETUP_SH = REPO_ROOT / "setup.sh"


def _setup_text() -> str:
    return SETUP_SH.read_text()


# ===========================================================================
# hyprconf-power-monitor script tests
# ===========================================================================


def _build_sysfs(
    tmp: Path,
    *,
    ac_online: int = 1,
    has_battery: bool = True,
    extra_mains: list[int] | None = None,
) -> Path:
    """Create a fake sysfs power_supply tree.

    `extra_mains` adds further Mains-type supplies — modern laptops publish one
    per USB-C port alongside the barrel jack.
    """
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

    for index, online in enumerate(extra_mains or []):
        port = sysfs / f"ucsi-source-psy-USBC000:{index:03d}"
        port.mkdir(exist_ok=True)
        (port / "type").write_text("Mains")
        (port / "online").write_text(str(online))

    return sysfs


def _run_monitor(
    tmp: Path,
    *,
    ac_online: int = 1,
    has_battery: bool = True,
    args: list[str] | None = None,
    has_powerprofilesctl: bool = True,
    profiles: tuple[str, ...] = ("performance", "balanced", "power-saver"),
    extra_mains: list[int] | None = None,
    remembered: dict[str, str] | None = None,
    current_profile: str = "balanced",
) -> tuple[int, str, str, list[str]]:
    """Run hyprconf-power-monitor with faked sysfs and powerprofilesctl.

    Returns (rc, stdout, stderr, powerprofilesctl_calls).
    """
    tmp.mkdir(parents=True, exist_ok=True)
    fake_dir = tmp / "fakebin"
    fake_dir.mkdir(exist_ok=True)
    calls_file = tmp / "pp_calls.txt"
    profile_file = tmp / "current_profile"
    profile_file.write_text(current_profile)

    if has_powerprofilesctl:
        # `powerprofilesctl list` prints "  name:" headers, with "*" marking the
        # active one — the format the script parses to learn what this machine
        # actually offers.
        listing = "".join(
            f"{'*' if name == current_profile else ' '} {name}:\n    CpuDriver:\tamd_pstate\n\n"
            for name in profiles
        )
        fake_pp = fake_dir / "powerprofilesctl"
        fake_pp.write_text(
            f"""#!/usr/bin/env bash
if [[ "$1" == "get" ]]; then
    cat "{profile_file}"
elif [[ "$1" == "set" ]]; then
    if ! printf '%s\\n' {" ".join(profiles)} | grep -qx -- "$2"; then
        echo "unknown profile" >&2
        exit 1
    fi
    echo "$2" > "{profile_file}"
    echo "set $2" >> "{calls_file}"
elif [[ "$1" == "list" ]]; then
    cat <<'LISTEOF'
{listing}LISTEOF
fi
"""
        )
        fake_pp.chmod(0o755)

    fake_logger = fake_dir / "logger"
    fake_logger.write_text("#!/usr/bin/env bash\n# no-op\n")
    fake_logger.chmod(0o755)

    sysfs = _build_sysfs(tmp, ac_online=ac_online, has_battery=has_battery, extra_mains=extra_mains)

    state_dir = tmp / "state"
    state_dir.mkdir(exist_ok=True)
    for state, profile in (remembered or {}).items():
        (state_dir / f"power-profile.{state}").write_text(f"{profile}\n")

    env = os.environ.copy()
    if has_powerprofilesctl:
        env["PATH"] = f"{fake_dir}:{env['PATH']}"
    else:
        # Hermetic "not installed": PATH must hold ONLY the fake dir, or a real
        # host powerprofilesctl leaks in and the outcome depends on host state
        # (its Python deps, the current profile, polkit). Bash builtins cover
        # everything else the script needs; the fake logger is best-effort.
        env["PATH"] = str(fake_dir)
    env["_HYPRCONF_PS_ROOT"] = str(sysfs)
    env["_HYPRCONF_STATE_DIR"] = str(state_dir)

    result = subprocess.run(
        [shutil.which("bash") or "bash", str(POWER_MONITOR)] + (args or []),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    calls: list[str] = []
    if calls_file.exists():
        calls = [ln.strip() for ln in calls_file.read_text().splitlines() if ln.strip()]

    return result.returncode, result.stdout, result.stderr, calls


def _remembered(tmp: Path, state: str) -> str:
    path = tmp / "state" / f"power-profile.{state}"
    return path.read_text().strip() if path.exists() else ""


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


class TestRememberedProfiles:
    """A profile chosen by hand must survive the next plug/unplug cycle.

    The automation used to force performance/power-saver on every AC event, so
    picking balanced on battery held only until the next transition.
    """

    def test_remembered_profile_wins_over_the_default(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(
            tmp_path,
            ac_online=0,
            remembered={"battery": "balanced"},
            current_profile="power-saver",
        )
        assert rc == 0
        assert "set balanced" in calls
        assert "set power-saver" not in calls

    def test_each_power_state_is_remembered_separately(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(
            tmp_path,
            ac_online=1,
            remembered={"ac": "balanced", "battery": "power-saver"},
            current_profile="power-saver",
        )
        assert rc == 0
        assert "set balanced" in calls

    def test_set_applies_and_remembers_for_the_current_state(self, tmp_path: Path) -> None:
        rc, stdout, _, calls = _run_monitor(
            tmp_path, ac_online=0, args=["set", "balanced"], current_profile="power-saver"
        )
        assert rc == 0
        assert "set balanced" in calls
        assert _remembered(tmp_path, "battery") == "balanced"
        assert _remembered(tmp_path, "ac") == ""
        assert "remembered for battery" in stdout

    def test_set_refuses_a_profile_the_daemon_does_not_offer(self, tmp_path: Path) -> None:
        rc, _, stderr, calls = _run_monitor(
            tmp_path, profiles=("balanced", "power-saver"), args=["set", "performance"]
        )
        assert rc != 0
        assert calls == []
        assert "Unknown power profile" in stderr

    def test_a_remembered_profile_that_disappeared_is_ignored(self, tmp_path: Path) -> None:
        """Firmware and driver changes can retire a profile between boots."""
        rc, _, _, calls = _run_monitor(
            tmp_path,
            ac_online=1,
            profiles=("balanced", "power-saver"),
            remembered={"ac": "performance"},
            current_profile="power-saver",
        )
        assert rc == 0
        assert "set balanced" in calls


class TestProfileAvailability:
    """Plenty of laptops expose only balanced and power-saver."""

    def test_falls_back_when_performance_is_unavailable(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(
            tmp_path,
            ac_online=1,
            profiles=("balanced", "power-saver"),
            current_profile="power-saver",
        )
        assert rc == 0
        assert "set balanced" in calls

    def test_falls_back_when_power_saver_is_unavailable(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(
            tmp_path,
            ac_online=0,
            profiles=("performance", "balanced"),
            current_profile="performance",
        )
        assert rc == 0
        assert "set balanced" in calls

    def test_the_profile_is_never_reapplied_when_it_already_matches(self, tmp_path: Path) -> None:
        """A machine offering only balanced is already on it; every AC event
        must not re-issue the same set."""
        rc, _, _, calls = _run_monitor(
            tmp_path, ac_online=1, profiles=("balanced",), current_profile="balanced"
        )
        assert rc == 0
        assert calls == []


class TestMultipleMainsSupplies:
    """A laptop publishes one Mains supply per USB-C port plus the barrel jack.

    Deciding from the first one found reported "on battery" while charging over
    USB-C, and dropped the machine to power-saver while plugged in.
    """

    def test_charging_over_usb_c_counts_as_ac(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, ac_online=0, extra_mains=[1])
        assert rc == 0
        assert "set performance" in calls

    def test_every_mains_offline_is_battery(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, ac_online=0, extra_mains=[0, 0])
        assert rc == 0
        assert "set power-saver" in calls


class TestMachinesWithoutABattery:
    """Automatic switching is laptop-only, but the tool still works."""

    def test_auto_leaves_a_desktop_alone(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, has_battery=False)
        assert rc == 0
        assert calls == []

    def test_status_still_reports(self, tmp_path: Path) -> None:
        rc, stdout, _, _ = _run_monitor(tmp_path, has_battery=False, args=["status"])
        assert rc == 0
        assert "no battery" in stdout

    def test_set_still_works(self, tmp_path: Path) -> None:
        rc, _, _, calls = _run_monitor(tmp_path, has_battery=False, args=["set", "performance"])
        assert rc == 0
        assert "set performance" in calls
        assert _remembered(tmp_path, "ac") == "performance"


class TestStatusDetail:
    def test_status_lists_available_profiles(self, tmp_path: Path) -> None:
        _, stdout, _, _ = _run_monitor(
            tmp_path, profiles=("balanced", "power-saver"), args=["status"]
        )
        assert "Available:" in stdout
        assert "balanced" in stdout
        assert "power-saver" in stdout

    def test_status_shows_remembered_choices(self, tmp_path: Path) -> None:
        _, stdout, _, _ = _run_monitor(
            tmp_path, remembered={"battery": "balanced"}, args=["status"]
        )
        assert "Remembered battery: balanced" in stdout
        assert "Remembered ac:      (default)" in stdout


class TestSessionStart:
    """power-profiles-daemon starts each boot on its own default and the udev
    rule only fires on *changes*, so a laptop booted on battery would sit on
    the AC profile until it was next unplugged."""

    def test_hyprland_applies_the_profile_at_session_start(self) -> None:
        hyprland_lua = REPO_ROOT / "stow/hypr/.config/hypr/hyprland.lua"
        assert 'hl.exec_cmd("hyprconf-power-monitor auto")' in hyprland_lua.read_text()
