"""Unit / functional tests for the quickshell bar's polling/streaming scripts.

battery_power_status.sh and cpu_temp.sh run on 1-2s ScriptModule intervals, so
they are written to be near-zero-cost: battery reads /sys/class/power_supply in
pure bash (root overridable via HYPRCONF_PS_ROOT), cpu_temp makes exactly one
`sensors` call. stats.sh is the long-lived cpu/mem/net sampler streamed by
Bar.qml; all of its system paths are HYPRCONF_STATS_*-overridable. These tests
drive them hermetically with fake sysfs/proc trees and fake binaries.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "stow" / "quickshell" / ".config" / "quickshell" / "scripts"
BATTERY_SH = SCRIPTS_DIR / "battery_power_status.sh"
CPU_TEMP_SH = SCRIPTS_DIR / "cpu_temp.sh"
STATS_SH = SCRIPTS_DIR.parent / "stats.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_exe(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _fake_battery(
    tmp_path: Path,
    *,
    capacity: str = "85",
    status: str = "Discharging",
    power_now: str | None = "12345678",
    current_now: str | None = None,
    voltage_now: str | None = None,
) -> Path:
    """Create a fake /sys/class/power_supply tree with one BAT0."""
    ps_root = tmp_path / "power_supply"
    bat = ps_root / "BAT0"
    bat.mkdir(parents=True)
    (bat / "capacity").write_text(capacity + "\n")
    (bat / "status").write_text(status + "\n")
    if power_now is not None:
        (bat / "power_now").write_text(power_now + "\n")
    if current_now is not None:
        (bat / "current_now").write_text(current_now + "\n")
    if voltage_now is not None:
        (bat / "voltage_now").write_text(voltage_now + "\n")
    return ps_root


def _run_battery(ps_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(BATTERY_SH)],
        capture_output=True,
        text=True,
        env={**os.environ, "HYPRCONF_PS_ROOT": str(ps_root)},
    )


def _run_cpu_temp(tmp_path: Path, sensors_output: str | None) -> subprocess.CompletedProcess:
    """Run cpu_temp.sh with a fake `sensors` binary (None = no sensors at all)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if sensors_output is not None:
        fixture = tmp_path / "sensors_output.txt"
        fixture.write_text(sensors_output)
        _write_exe(bin_dir / "sensors", f'#!/usr/bin/env bash\ncat "{fixture}"\n')
        path = f"{bin_dir}:{os.environ['PATH']}"
    else:
        # PATH holds only the empty fake dir, so `command -v sensors` fails and
        # the script must exit 0 silently before needing any external tool.
        path = str(bin_dir)
    return subprocess.run(
        [shutil.which("bash") or "bash", str(CPU_TEMP_SH)],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": path},
    )


# ---------------------------------------------------------------------------
# battery_power_status.sh
# ---------------------------------------------------------------------------


class TestBatteryScript:
    def test_no_battery_reports_ac(self, tmp_path: Path) -> None:
        ps_root = tmp_path / "power_supply"
        ps_root.mkdir()
        r = _run_battery(ps_root)
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["class"] == "ac"

    def test_discharging_battery_payload(self, tmp_path: Path) -> None:
        ps_root = _fake_battery(tmp_path)  # 85%, 12345678 µW
        r = _run_battery(ps_root)
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["class"] == "normal"
        assert "85%" in payload["text"]
        assert "(12.35 W)" in payload["text"]  # rounded to 2 decimals

    def test_charging_class(self, tmp_path: Path) -> None:
        ps_root = _fake_battery(tmp_path, status="Charging")
        payload = json.loads(_run_battery(ps_root).stdout)
        assert payload["class"] == "charging"

    def test_critical_and_warning_thresholds(self, tmp_path: Path) -> None:
        payload = json.loads(_run_battery(_fake_battery(tmp_path, capacity="10")).stdout)
        assert payload["class"] == "critical"
        payload = json.loads(_run_battery(_fake_battery(tmp_path / "w", capacity="25")).stdout)
        assert payload["class"] == "warning"

    def test_current_voltage_fallback(self, tmp_path: Path) -> None:
        # 1 A × 12 V = 12 W via current_now/voltage_now when power_now is absent.
        ps_root = _fake_battery(
            tmp_path,
            power_now=None,
            current_now="1000000",
            voltage_now="12000000",
        )
        payload = json.loads(_run_battery(ps_root).stdout)
        assert "(12.00 W)" in payload["text"]

    def test_negative_power_now_uses_magnitude(self, tmp_path: Path) -> None:
        ps_root = _fake_battery(tmp_path, power_now="-5000000")
        payload = json.loads(_run_battery(ps_root).stdout)
        assert "(5.00 W)" in payload["text"]

    def test_no_subprocesses_in_script(self) -> None:
        """The 1s poll path must stay pure bash — no external commands.

        upower/grep/awk pipelines here cost ~12 process spawns per second.
        """
        code_lines = [
            ln
            for ln in BATTERY_SH.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        for banned in ("upower", "awk", "grep", "sed", " cat "):
            assert banned not in code, f"battery script must not spawn {banned!r}"


# ---------------------------------------------------------------------------
# cpu_temp.sh
# ---------------------------------------------------------------------------

AMD_SENSORS = """\
k10temp-pci-00c3
Adapter: PCI adapter
Tctl:         +54.3°C
Tdie:         +52.0°C
"""

INTEL_SENSORS = """\
coretemp-isa-0000
Adapter: ISA adapter
Package id 0:  +47.0°C  (high = +80.0°C, crit = +100.0°C)
Core 0:        +45.0°C  (high = +80.0°C, crit = +100.0°C)
Core 1:        +46.0°C  (high = +80.0°C, crit = +100.0°C)
"""


class TestCpuTempScript:
    def test_amd_tctl_wins(self, tmp_path: Path) -> None:
        r = _run_cpu_temp(tmp_path, AMD_SENSORS)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["text"] == "54°"

    def test_intel_package_wins_over_core(self, tmp_path: Path) -> None:
        r = _run_cpu_temp(tmp_path, INTEL_SENSORS)
        assert json.loads(r.stdout)["text"] == "47°"

    def test_priority_tctl_beats_package_even_if_later(self, tmp_path: Path) -> None:
        r = _run_cpu_temp(tmp_path, INTEL_SENSORS + AMD_SENSORS)
        assert json.loads(r.stdout)["text"] == "54°"

    def test_no_temp_lines_hides_module(self, tmp_path: Path) -> None:
        r = _run_cpu_temp(tmp_path, "acpitz-acpi-0\nAdapter: ACPI interface\n")
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_missing_sensors_hides_module(self, tmp_path: Path) -> None:
        r = _run_cpu_temp(tmp_path, None)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_single_sensors_invocation(self) -> None:
        """The script must call sensors exactly once per poll (plus the
        `command -v` guard) — re-running it per label was the old hot-path bug."""
        text = CPU_TEMP_SH.read_text(encoding="utf-8")
        calls = [
            ln
            for ln in text.splitlines()
            if "sensors" in ln and "command -v" not in ln and not ln.strip().startswith("#")
        ]
        assert len(calls) == 1, f"expected exactly one sensors call, got: {calls}"


# ---------------------------------------------------------------------------
# stats.sh (streaming cpu/mem/net sampler)
# ---------------------------------------------------------------------------

PROC_STAT = "cpu  100 0 100 800 0 0 0 0 0 0\n"
PROC_MEMINFO = "MemTotal:       33554432 kB\nMemAvailable:   16777216 kB\n"


def _fake_net(tmp_path: Path, *, wired_up: bool = True, wifi: bool = True) -> Path:
    """Fake /sys/class/net with one physical wired + one wireless interface."""
    net = tmp_path / "net"
    eth = net / "eth0"
    (eth / "statistics").mkdir(parents=True)
    (eth / "device").write_text("")  # physical-interface marker
    (eth / "operstate").write_text("up\n" if wired_up else "down\n")
    (eth / "statistics" / "rx_bytes").write_text("1000\n")
    (eth / "statistics" / "tx_bytes").write_text("2000\n")
    if wifi:
        wl = net / "wlan0"
        (wl / "statistics").mkdir(parents=True)
        (wl / "wireless").mkdir()
        (wl / "device").write_text("")
        (wl / "operstate").write_text("up\n")
        (wl / "statistics" / "rx_bytes").write_text("5000\n")
        (wl / "statistics" / "tx_bytes").write_text("6000\n")
    (net / "lo").mkdir()  # must be skipped by name
    return net


def _run_stats(
    tmp_path: Path,
    net_root: Path,
    *,
    default_route_dev: str | None = "wlan0",
    iterations: int = 2,
) -> list[dict]:
    """Run stats.sh hermetically for N samples and parse its JSON lines."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    route = (
        f'echo "default via 192.168.1.1 dev {default_route_dev} proto dhcp"\n'
        if default_route_dev
        else "exit 0\n"
    )
    _write_exe(bin_dir / "ip", "#!/usr/bin/env bash\n" + route)
    stat_f = tmp_path / "proc_stat"
    stat_f.write_text(PROC_STAT)
    mem_f = tmp_path / "meminfo"
    mem_f.write_text(PROC_MEMINFO)
    r = subprocess.run(
        ["bash", str(STATS_SH)],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "HYPRCONF_STATS_NET_ROOT": str(net_root),
            "HYPRCONF_STATS_PROC_STAT": str(stat_f),
            "HYPRCONF_STATS_PROC_MEMINFO": str(mem_f),
            "HYPRCONF_STATS_INTERVAL": "0",
            "HYPRCONF_STATS_ITERATIONS": str(iterations),
        },
    )
    assert r.returncode == 0, r.stderr
    return [json.loads(ln) for ln in r.stdout.strip().splitlines()]


class TestStatsScript:
    def test_emits_valid_json_samples(self, tmp_path: Path) -> None:
        lines = _run_stats(tmp_path, _fake_net(tmp_path), iterations=2)
        assert len(lines) == 2
        for payload in lines:
            assert set(payload) == {"cpu", "mem", "net", "down", "up"}
            assert isinstance(payload["cpu"], int)
        assert lines[0]["mem"] == "16.0/32.0G"  # MemTotal-MemAvailable, GiB

    def test_ethernet_precedence_over_wifi_default_route(self, tmp_path: Path) -> None:
        """A wired link that is up must win over the (wifi) default route.

        Regression: `$(<file 2>/dev/null)` captures "" on bash 5.3, which made
        the operstate check silently never match, disabling this feature.
        """
        net = _fake_net(tmp_path, wired_up=True)
        payload = _run_stats(tmp_path, net, default_route_dev="wlan0", iterations=1)[0]
        assert payload["net"] == "eth"

    def test_wifi_fallback_when_no_wired_link(self, tmp_path: Path) -> None:
        net = _fake_net(tmp_path, wired_up=False)
        payload = _run_stats(tmp_path, net, default_route_dev="wlan0", iterations=1)[0]
        assert payload["net"] == "wifi"

    def test_off_when_no_interfaces_and_no_route(self, tmp_path: Path) -> None:
        net = tmp_path / "net"
        (net / "lo").mkdir(parents=True)
        payload = _run_stats(tmp_path, net, default_route_dev=None, iterations=1)[0]
        assert payload["net"] == "off"
        assert payload["down"] == "0B/s"
