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


# ---------------------------------------------------------------------------
# hyprconf-gpu-info (streaming: nvidia-smi --loop | awk, or AMD sysfs loop)
# ---------------------------------------------------------------------------

GPU_KEYS = {"index", "name", "util", "temp", "vram_used", "vram_total", "tooltip"}

# Two GPUs, two iterations. Iteration 1: index 1 is the busy card (the real
# two-card shape: 3070 idling at 2 MiB, 5090 working). Iteration 2 flips the
# load onto index 0 so the selection must follow it.
NVIDIA_TWO_GPU_LINES = [
    "0, NVIDIA GeForce RTX 3070, 0, 20.11, 31, 2, 8192",
    "1, NVIDIA GeForce RTX 5090, 7, 45.20, 36, 2314, 32607",
    "0, NVIDIA GeForce RTX 3070, 55, 180.00, 62, 6000, 8192",
    "1, NVIDIA GeForce RTX 5090, 1, 30.00, 35, 300, 32607",
]


def _fake_nvidia_smi(count: int, lines: list[str]) -> str:
    """Fake nvidia-smi: the count query prints one line per GPU each holding
    the total (the real shape); any other probe exits 0 quietly; the stream
    (-l) emits `lines` (GPUs consecutive per iteration) and stops."""
    count_out = "".join(f"{count}\\n" for _ in range(count))
    stream = "\n".join('        echo "' + ln.replace('"', '\\"') + '"' for ln in lines)
    return f"""\
#!/usr/bin/env bash
for a in "$@"; do
    case $a in
        --query-gpu=count) printf '{count_out}'; exit 0 ;;
        -l)
{stream}
        exit 0 ;;
    esac
done
exit 0
"""


FAKE_NVIDIA_SMI = _fake_nvidia_smi(2, NVIDIA_TWO_GPU_LINES)


class TestGpuInfoScript:
    def _run(
        self,
        tmp_path: Path,
        *,
        nvidia: bool | str,
        drm_root: Path | None = None,
        env=None,
    ) -> subprocess.CompletedProcess[str]:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        # Always shadow nvidia-smi: on a real NVIDIA host the genuine binary
        # would otherwise answer the probe and stream real data into the test.
        if nvidia is True:
            fake = FAKE_NVIDIA_SMI
        elif nvidia:
            fake = nvidia
        else:
            fake = "#!/usr/bin/env bash\nexit 1\n"
        _write_exe(bin_dir / "nvidia-smi", fake)
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

    def _lines(self, r: subprocess.CompletedProcess[str]) -> list[dict]:
        assert r.returncode == 0, r.stderr
        lines = [json.loads(ln) for ln in r.stdout.strip().splitlines()]
        for payload in lines:
            assert set(payload) == GPU_KEYS
            assert isinstance(payload["index"], int)
            assert isinstance(payload["name"], str)
            assert isinstance(payload["util"], int)
            assert payload["temp"] is None or isinstance(payload["temp"], int)
            assert isinstance(payload["vram_used"], str)
            assert isinstance(payload["vram_total"], str)
        return lines

    @staticmethod
    def _amd_card(
        drm: Path,
        n: int,
        *,
        busy: str,
        used: int | None,
        total: int | None,
        temp: str | None = None,
        name: str | None = None,
    ) -> Path:
        card = drm / f"card{n}" / "device"
        card.mkdir(parents=True)
        (card / "gpu_busy_percent").write_text(busy + "\n")
        if used is not None:
            (card / "mem_info_vram_used").write_text(str(used) + "\n")
        if total is not None:
            (card / "mem_info_vram_total").write_text(str(total) + "\n")
        if temp is not None:
            hw = card / "hwmon" / "hwmon3"
            hw.mkdir(parents=True)
            (hw / "temp1_input").write_text(temp + "\n")
        if name is not None:
            (card / "product_name").write_text(name + "\n")
        return card

    # -- NVIDIA ---------------------------------------------------------------

    def test_nvidia_two_gpus_follow_the_busy_card(self, tmp_path: Path) -> None:
        lines = self._lines(self._run(tmp_path, nvidia=True))
        assert len(lines) == 2  # one JSON line per iteration, not per GPU
        first, second = lines
        assert first["index"] == 1
        assert first["name"] == "NVIDIA GeForce RTX 5090"
        assert first["util"] == 7
        assert first["temp"] == 36
        assert first["vram_used"] == "2.3"
        assert first["vram_total"] == "31.8"
        assert first["tooltip"] == (
            "RTX 5090 (GPU 1) | Util 7% | Temp 36° | VRAM 2.3/31.8 GiB | Power 45W"
        )
        # Iteration 2: the load moved to index 0, so the selection flips.
        assert second["index"] == 0
        assert second["name"] == "NVIDIA GeForce RTX 3070"
        assert second["util"] == 55
        assert second["temp"] == 62
        assert second["vram_used"] == "5.9"
        assert second["vram_total"] == "8.0"
        assert "RTX 3070" in second["tooltip"]

    def test_nvidia_single_gpu(self, tmp_path: Path) -> None:
        fake = _fake_nvidia_smi(
            1,
            [
                "0, NVIDIA GeForce RTX 4080, 12, 100.5, 55, 8192, 16384",
                "0, NVIDIA GeForce RTX 4080, 34, 200.0, 60, 12288, 16384",
            ],
        )
        lines = self._lines(self._run(tmp_path, nvidia=fake))
        assert [ln["util"] for ln in lines] == [12, 34]
        assert lines[0]["index"] == 0
        assert lines[0]["vram_used"] == "8.0"
        assert lines[1]["vram_used"] == "12.0"
        assert lines[1]["vram_total"] == "16.0"

    def test_nvidia_name_with_comma_parses(self, tmp_path: Path) -> None:
        fake = _fake_nvidia_smi(1, ['0, NVIDIA "Ada", Ltd 4090, 9, 50.0, 40, 1024, 24576'])
        line = self._lines(self._run(tmp_path, nvidia=fake))[0]
        assert line["name"] == 'NVIDIA "Ada", Ltd 4090'  # quotes escaped, comma kept
        assert line["util"] == 9
        assert line["temp"] == 40
        assert line["vram_used"] == "1.0"
        assert line["vram_total"] == "24.0"

    def test_nvidia_memory_tie_broken_by_util(self, tmp_path: Path) -> None:
        fake = _fake_nvidia_smi(
            2,
            [
                "0, NVIDIA A, 3, 10.0, 30, 500, 8192",
                "1, NVIDIA B, 9, 10.0, 30, 500, 8192",
                # Full tie → lowest index.
                "0, NVIDIA A, 9, 10.0, 30, 500, 8192",
                "1, NVIDIA B, 9, 10.0, 30, 500, 8192",
            ],
        )
        lines = self._lines(self._run(tmp_path, nvidia=fake))
        assert [ln["index"] for ln in lines] == [1, 0]

    def test_nvidia_unknown_temp_is_null(self, tmp_path: Path) -> None:
        fake = _fake_nvidia_smi(1, ["0, NVIDIA T, 1, [N/A], [N/A], 100, 8192"])
        line = self._lines(self._run(tmp_path, nvidia=fake))[0]
        assert line["temp"] is None
        assert "Power" not in line["tooltip"]

    # -- AMD ------------------------------------------------------------------

    def test_amd_two_cards_pick_more_vram_used(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._amd_card(drm, 1, busy="90", used=1 * 1024**3, total=16 * 1024**3, temp="50000")
        self._amd_card(
            drm,
            2,
            busy="42",
            used=4 * 1024**3,
            total=16 * 1024**3,
            temp="61000",
            name="Radeon RX 7900 XTX",
        )
        lines = self._lines(self._run(tmp_path, nvidia=False, drm_root=drm))
        assert len(lines) == 2  # HYPRCONF_GPU_ITERATIONS bounds the loop
        line = lines[0]
        assert line["index"] == 2  # more memory used beats higher busy %
        assert line["name"] == "Radeon RX 7900 XTX"
        assert line["util"] == 42
        assert line["temp"] == 61
        assert line["vram_used"] == "4.0"
        assert line["vram_total"] == "16.0"
        assert line["tooltip"] == (
            "Radeon RX 7900 XTX (GPU 2) | Util 42% | Temp 61° | VRAM 4.0/16.0 GiB"
        )

    def test_amd_memory_tie_broken_by_busy_then_index(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._amd_card(drm, 1, busy="10", used=100, total=16 * 1024**3)
        self._amd_card(drm, 2, busy="20", used=100, total=16 * 1024**3)
        self._amd_card(drm, 0, busy="20", used=100, total=16 * 1024**3)
        line = self._lines(self._run(tmp_path, nvidia=False, drm_root=drm))[0]
        assert line["index"] == 0

    def test_amd_no_hwmon_and_no_name(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._amd_card(drm, 1, busy="5", used=2 * 1024**3, total=8 * 1024**3)
        line = self._lines(self._run(tmp_path, nvidia=False, drm_root=drm))[0]
        assert line["name"] == ""
        assert line["temp"] is None
        assert line["tooltip"].startswith("GPU 1 (GPU 1) | Util 5% | Temp n/a")

    def test_amd_igpu_without_vram_files_is_shared(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._amd_card(drm, 0, busy="3", used=None, total=None, name="Raphael")
        line = self._lines(self._run(tmp_path, nvidia=False, drm_root=drm))[0]
        assert line["vram_total"] == "0"
        assert line["vram_used"] == "0.0"
        assert line["tooltip"].endswith("| VRAM shared")

    def test_amd_ignores_connector_nodes(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._amd_card(drm, 1, busy="3", used=100, total=8 * 1024**3)
        # A connector's device/ points back at the card; the glob prefix
        # matches it but it must not be counted as a second GPU.
        conn = drm / "card1-DP-1" / "device"
        conn.mkdir(parents=True)
        (conn / "gpu_busy_percent").write_text("99\n")
        line = self._lines(self._run(tmp_path, nvidia=False, drm_root=drm))[0]
        assert line["index"] == 1
        assert line["util"] == 3

    # -- neither --------------------------------------------------------------

    def test_no_gpu_exits_silently(self, tmp_path: Path) -> None:
        r = self._run(tmp_path, nvidia=False)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
