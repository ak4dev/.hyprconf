"""Unit / functional tests for the two streaming feeders behind the
hyprconf.resources bar widget (plugins/hyprconf-resources/Widget.qml).

bin/hyprconf-stats is the long-lived cpu/mem/net/temp sampler (cpu temperature
is read straight from a hwmon path resolved once at startup); all of its system
paths are HYPRCONF_STATS_*-overridable. bin/hyprconf-gpu-info is a long-lived
stream too: nvidia-smi --loop piped through one awk, or a pure-bash AMD sysfs
loop (HYPRCONF_GPU_*-overridable). These tests drive them hermetically with
fake sysfs/proc trees and fake binaries.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
GPU_INFO_SH = REPO_ROOT / "bin" / "hyprconf-gpu-info"
STATS_SH = REPO_ROOT / "bin" / "hyprconf-stats"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_exe(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _fake_hwmon(tmp_path: Path, sensors: list[tuple[str, str]]) -> Path:
    """Create a fake /sys/class/hwmon tree: one chip per (label, millideg)."""
    root = tmp_path / "hwmon"
    root.mkdir(exist_ok=True)
    for i, (label, mdeg) in enumerate(sensors):
        chip = root / f"hwmon{i}"
        chip.mkdir()
        (chip / "temp1_label").write_text(label + "\n")
        (chip / "temp1_input").write_text(mdeg + "\n")
    return root


# ---------------------------------------------------------------------------
# stats.sh (streaming cpu/mem/net/temp sampler)
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
    route_line: str | None = None,
    iterations: int = 2,
    hwmon_root: Path | None = None,
) -> list[dict]:
    """Run stats.sh hermetically for N samples and parse its JSON lines.

    `route_line` overrides the fake `ip route show default` output verbatim
    (for route shapes beyond the standard `via <gw> dev <iface>` form).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if route_line is not None:
        route = f'echo "{route_line}"\n'
    elif default_route_dev:
        route = f'echo "default via 192.168.1.1 dev {default_route_dev} proto dhcp"\n'
    else:
        route = "exit 0\n"
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
            # empty tree by default → temp resolves to "" (hidden module)
            "HYPRCONF_STATS_HWMON_ROOT": str(hwmon_root or _fake_hwmon(tmp_path, [])),
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
            assert set(payload) == {"cpu", "mem", "net", "down", "up", "temp"}
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

    def test_vpn_tunnel_default_route_without_gateway(self, tmp_path: Path) -> None:
        """WireGuard/OpenVPN default routes have no gateway hop — `ip route
        show default` prints `default dev wg0 scope link`, not `default via
        <gw> dev wg0 ...`. The interface must be parsed as the token after
        `dev`: a fixed `$5` parse reads "link" here, and the bar showed
        "Disconnected" while the VPN carried all traffic.
        """
        net = _fake_net(tmp_path, wired_up=False, wifi=False)
        wg = net / "wg0"
        (wg / "statistics").mkdir(parents=True)
        # Tunnels are virtual: no device/ marker (so the wired-precedence scan
        # must skip it), no wireless/ dir; wg operstate reads "unknown".
        (wg / "operstate").write_text("unknown\n")
        (wg / "statistics" / "rx_bytes").write_text("7000\n")
        (wg / "statistics" / "tx_bytes").write_text("8000\n")
        payload = _run_stats(tmp_path, net, route_line="default dev wg0 scope link", iterations=1)[
            0
        ]
        assert payload["net"] == "eth"  # non-wifi iface renders the wired icon
        assert payload["down"] == "0B/s"


# ---------------------------------------------------------------------------
# stats.sh cpu temperature (hwmon, resolved once — replaced cpu_temp.sh)
# ---------------------------------------------------------------------------


class TestStatsCpuTemp:
    def _temp(self, tmp_path: Path, sensors: list[tuple[str, str]]) -> str:
        hwmon = _fake_hwmon(tmp_path, sensors)
        net = tmp_path / "net"
        (net / "lo").mkdir(parents=True)
        payload = _run_stats(tmp_path, net, default_route_dev=None, iterations=1, hwmon_root=hwmon)[
            0
        ]
        return payload["temp"]

    def test_amd_tctl_wins_over_tdie(self, tmp_path: Path) -> None:
        assert self._temp(tmp_path, [("Tdie", "52000"), ("Tctl", "54300")]) == "54°"

    def test_intel_package_wins_over_core(self, tmp_path: Path) -> None:
        assert self._temp(tmp_path, [("Core 0", "45000"), ("Package id 0", "47000")]) == "47°"

    def test_tctl_beats_package_even_if_later_chip(self, tmp_path: Path) -> None:
        assert self._temp(tmp_path, [("Package id 0", "47000"), ("Tctl", "54300")]) == "54°"

    def test_rounds_millidegrees(self, tmp_path: Path) -> None:
        assert self._temp(tmp_path, [("Tctl", "54500")]) == "55°"

    def test_no_cpu_labels_hides_module(self, tmp_path: Path) -> None:
        # GPU/NVMe-style hwmon chips must not be mistaken for the CPU sensor.
        assert self._temp(tmp_path, [("Composite", "38000"), ("edge", "60000")]) == ""

    def test_no_hwmon_tree_hides_module(self, tmp_path: Path) -> None:
        assert self._temp(tmp_path, []) == ""

    def test_no_sensors_binary_needed(self) -> None:
        """Temperature must come from hwmon files, not a per-poll `sensors`
        subprocess (the pre-streaming design)."""
        code = "\n".join(
            ln
            for ln in STATS_SH.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("#")
        )
        assert "sensors" not in code


# ---------------------------------------------------------------------------
# gpu_info.sh (streaming: nvidia-smi --loop | awk, or AMD sysfs loop)
# ---------------------------------------------------------------------------

FAKE_NVIDIA_SMI = """\
#!/usr/bin/env bash
# Probe (no -l): exit 0 quietly. Stream (-l): emit two CSV samples and stop.
for a in "$@"; do
    if [[ $a == -l ]]; then
        echo "12, 100.5, 55, 8192, 32768"
        echo "34, 200.0, 60, 16384, 32768"
        exit 0
    fi
done
exit 0
"""


class TestGpuInfoScript:
    def _run(self, tmp_path: Path, *, nvidia: bool, drm_root: Path | None = None, env=None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        # Always shadow nvidia-smi: on a real NVIDIA host the genuine binary
        # would otherwise answer the probe and stream real data into the test.
        _write_exe(
            bin_dir / "nvidia-smi",
            FAKE_NVIDIA_SMI if nvidia else "#!/usr/bin/env bash\nexit 1\n",
        )
        extra = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "HYPRCONF_GPU_DRM_ROOT": str(drm_root or (tmp_path / "drm-empty")),
            "HYPRCONF_GPU_ITERATIONS": "2",
            "HYPRCONF_GPU_INTERVAL": "0",
            **(env or {}),
        }
        return subprocess.run(
            ["bash", str(GPU_INFO_SH)],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, **extra},
        )

    def test_nvidia_stream_formats_each_sample(self, tmp_path: Path) -> None:
        r = self._run(tmp_path, nvidia=True)
        assert r.returncode == 0, r.stderr
        lines = [json.loads(ln) for ln in r.stdout.strip().splitlines()]
        assert len(lines) == 2
        assert "12%" in lines[0]["text"]
        assert "8.0/32.0G" in lines[0]["text"]
        assert "55°" in lines[0]["text"]
        assert "34%" in lines[1]["text"]
        assert "16.0/32.0G" in lines[1]["text"]

    def test_amd_sysfs_loop(self, tmp_path: Path) -> None:
        card = tmp_path / "drm" / "card1" / "device"
        card.mkdir(parents=True)
        (card / "gpu_busy_percent").write_text("42\n")
        hw = card / "hwmon" / "hwmon3"
        hw.mkdir(parents=True)
        (hw / "temp1_input").write_text("61000\n")
        (card / "mem_info_vram_used").write_text(str(4 * 1024**3) + "\n")
        (card / "mem_info_vram_total").write_text(str(16 * 1024**3) + "\n")
        r = self._run(tmp_path, nvidia=False, drm_root=tmp_path / "drm")
        assert r.returncode == 0, r.stderr
        lines = [json.loads(ln) for ln in r.stdout.strip().splitlines()]
        assert len(lines) == 2  # HYPRCONF_GPU_ITERATIONS bounds the loop
        assert "42%" in lines[0]["text"]
        assert "61°" in lines[0]["text"]
        assert "4.0/16.0G" in lines[0]["text"]

    def test_no_gpu_exits_silently(self, tmp_path: Path) -> None:
        r = self._run(tmp_path, nvidia=False)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
