"""Unit / functional tests for the two streaming feeders behind the
hyprconf.resources bar widget (plugins/hyprconf-resources/Widget.qml), which
ship inside that plugin folder (plugins/hyprconf-resources/bin/) and are run
by absolute path from it.

hyprconf-stats is the long-lived cpu/mem/net/temp sampler (cpu temperature is
read straight from a hwmon path resolved once at startup; the default-route
interface from /proc/net/route); all of its system paths are
HYPRCONF_STATS_*-overridable, and a tick forks nothing. hyprconf-gpu-info is a
long-lived stream too: nvidia-smi --loop piped through one awk, or a
pure-bash sysfs loop over AMD's gpu_busy_percent or Intel's xe idle-residency
counter, the latter gated on power/runtime_status because every xe read
resumes the card (HYPRCONF_GPU_*-overridable). These tests drive them hermetically with
fake sysfs/proc trees and fake binaries; a PATH `sleep` fake is the hook that
runs between ticks (hyprconf-stats' loadable-sleep seam is pointed at a file
that is not there, so the fake is what its ticks call).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
# The feeders ship inside the plugin that runs them, by absolute path from
# its own folder — nothing on PATH.
FEEDERS = REPO_ROOT / "plugins" / "hyprconf-resources" / "bin"
GPU_INFO = FEEDERS / "hyprconf-gpu-info"
STATS = FEEDERS / "hyprconf-stats"


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
# hyprconf-stats (streaming cpu/mem/net/temp sampler)
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


# /proc/net/route as the kernel prints it (net/ipv4/fib_trie.c,
# fib_route_seq_show): a header, then one tab-separated line per route of the
# main table — Iface, Destination and Gateway as little-endian hex, Flags,
# RefCnt, Use, Metric, Mask, MTU, Window, IRTT — each padded to 127 columns.
ROUTE_HEADER = "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT"


def _route(iface: str, *, gateway: bool = True, metric: int = 600, dest: str = "00000000") -> str:
    """One route line: the default route (dest 00000000) via a gateway
    (RTF_UP|RTF_GATEWAY, 0003), or gateway-less the way a tunnel's is
    (Gateway 00000000, RTF_UP alone, 0001); `dest` for a non-default line."""
    gw, flags = ("0101A8C0", "0003") if gateway else ("00000000", "0001")
    mask = "00000000" if dest == "00000000" else "00FFFFFF"
    return f"{iface}\t{dest}\t{gw}\t{flags}\t0\t0\t{metric}\t{mask}\t0\t0\t0".ljust(127)


def _run_stats(
    tmp_path: Path,
    net_root: Path,
    *,
    route_dev: str | None = "wlan0",
    route_lines: list[str] | None = None,
    iterations: int = 2,
    hwmon_root: Path | None = None,
    sleep_body: str | None = None,
    env: dict[str, str] | None = None,
    bare_path: bool = False,
) -> list[dict]:
    """Run hyprconf-stats hermetically for N samples and parse its JSON lines.

    The fake /proc/net/route names `route_dev` as the default-route
    interface (`route_lines` replaces the generated route lines verbatim, for
    tables beyond one gateway route; `route_dev=None` lists no default route),
    and the PATH `sleep` fake that runs between ticks advances that
    interface's counters by 5000 rx / 1000 tx bytes on every call: a sample
    fed from it reads 5.0kB/s down and 1.0kB/s up, one fed from any other
    (static) interface reads 0B/s, so the rate says which interface the
    feeder read. `sleep_body` scripts the fake instead, for tests that mutate
    the tree between ticks. `bare_path` runs the feeder with the fake bin dir
    as the whole PATH — the pin that a tick execs nothing.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    # The fake `sleep`: the seam below keeps bash's loadable sleep out, so
    # every tick's `sleep` is this file. `command -p` then runs the real sleep
    # off the standard PATH, never this fake again. A bare PATH cannot resolve
    # `env`'s bash, so the shebang names the real one.
    bash = shutil.which("bash")
    assert bash, "bash not installed"
    sleep = f"#!{bash}\n"
    if sleep_body is not None:
        sleep += sleep_body
    elif route_dev is not None:
        stats = net_root / route_dev / "statistics"
        sleep += (
            f'read -r n < "{stats}/rx_bytes" && echo $((n + 5000)) > "{stats}/rx_bytes"\n'
            f'read -r n < "{stats}/tx_bytes" && echo $((n + 1000)) > "{stats}/tx_bytes"\n'
        )
    sleep += 'command -p sleep "$@"\n'
    _write_exe(bin_dir / "sleep", sleep)
    if route_lines is None:
        route_lines = [_route(route_dev)] if route_dev is not None else []
        route_lines.append(_route("wlan0", gateway=False, dest="0001A8C0"))  # the link route
    route_f = tmp_path / "proc_net_route"
    route_f.write_text("\n".join([ROUTE_HEADER.ljust(127), *route_lines]) + "\n")
    stat_f = tmp_path / "proc_stat"
    stat_f.write_text(PROC_STAT)
    mem_f = tmp_path / "meminfo"
    mem_f.write_text(PROC_MEMINFO)
    r = subprocess.run(
        [bash, str(STATS)],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "PATH": str(bin_dir) if bare_path else f"{bin_dir}:{os.environ['PATH']}",
            "HYPRCONF_STATS_NET_ROOT": str(net_root),
            "HYPRCONF_STATS_PROC_STAT": str(stat_f),
            "HYPRCONF_STATS_PROC_MEMINFO": str(mem_f),
            "HYPRCONF_STATS_PROC_ROUTE": str(route_f),
            # empty tree by default → temp resolves to "" (hidden module)
            "HYPRCONF_STATS_HWMON_ROOT": str(hwmon_root or _fake_hwmon(tmp_path, [])),
            # A file that is not there: the PATH fake above is the sleep.
            "HYPRCONF_STATS_SLEEP_BUILTIN": str(tmp_path / "no-loadable-sleep"),
            "HYPRCONF_STATS_INTERVAL": "0",
            "HYPRCONF_STATS_ITERATIONS": str(iterations),
            **(env or {}),
        },
    )
    assert r.returncode == 0, r.stderr
    # A feeder that complains repeats it every tick into the shell's journal.
    assert r.stderr == "", r.stderr
    return [json.loads(ln) for ln in r.stdout.strip().splitlines()]


class TestStatsScript:
    def test_emits_valid_json_samples(self, tmp_path: Path) -> None:
        lines = _run_stats(tmp_path, _fake_net(tmp_path), iterations=2)
        assert len(lines) == 2
        for payload in lines:
            assert set(payload) == {"cpu", "mem", "down", "up", "temp"}
            assert isinstance(payload["cpu"], int)
        assert lines[0]["mem"] == "16.0/32.0G"  # MemTotal-MemAvailable, GiB

    def test_ethernet_precedence_over_wifi_default_route(self, tmp_path: Path) -> None:
        """A wired link that is up must win over the (wifi) default route.

        `$(< file 2>/dev/null)` is empty on Bash 5.3 (AGENTS.md › Known
        quirks): read that way, the operstate check never matches and the
        rates come from wlan0.
        """
        net = _fake_net(tmp_path, wired_up=True)
        payload = _run_stats(tmp_path, net, route_dev="wlan0", iterations=1)[0]
        assert payload["down"] == "0B/s"  # eth0's static counters
        # wlan0 did move between the ticks: the 0B/s is eth0's, not a stalled hook.
        assert (net / "wlan0/statistics/rx_bytes").read_text() == "10000\n"

    def test_wifi_fallback_when_no_wired_link(self, tmp_path: Path) -> None:
        net = _fake_net(tmp_path, wired_up=False)
        payload = _run_stats(tmp_path, net, route_dev="wlan0", iterations=1)[0]
        assert (payload["down"], payload["up"]) == ("5.0kB/s", "1.0kB/s")

    def test_default_route_lookup_execs_nothing(self, tmp_path: Path) -> None:
        """The Wi-Fi/VPN path is the permanent state of most boxes and runs
        once a second for the whole session: it must fork nothing. With the fake
        bin dir as the whole PATH no `ip`, `awk` or coreutils exist — a
        lookup that shells out finds no interface and reads 0B/s."""
        net = _fake_net(tmp_path, wired_up=False)
        payload = _run_stats(tmp_path, net, route_dev="wlan0", iterations=1, bare_path=True)[0]
        assert (payload["down"], payload["up"]) == ("5.0kB/s", "1.0kB/s")

    def test_first_default_route_wins_and_the_rest_of_the_table_is_ignored(
        self, tmp_path: Path
    ) -> None:
        """The kernel lists a prefix's routes by metric (fib_insert_alias),
        so of two default routes the first is the one `ip route show default`
        prints first: a tether at metric 100 ahead of Wi-Fi at 600. Neither
        the header, a link route listed before them, nor an `unreachable
        default` (no device: "*", where `ip` prints no `dev`) may be taken
        for the interface."""
        net = _fake_net(tmp_path, wired_up=False)
        tether = net / "usb0"
        (tether / "statistics").mkdir(parents=True)
        (tether / "statistics" / "rx_bytes").write_text("100\n")
        (tether / "statistics" / "tx_bytes").write_text("200\n")
        payload = _run_stats(
            tmp_path,
            net,
            route_dev="usb0",
            route_lines=[
                _route("wlan0", gateway=False, dest="0001A8C0"),
                _route("*", metric=0),
                _route("usb0", metric=100),
                _route("wlan0", metric=600),
            ],
            iterations=1,
        )[0]
        assert (payload["down"], payload["up"]) == ("5.0kB/s", "1.0kB/s")

    def test_no_interface_and_no_route_reads_zero(self, tmp_path: Path) -> None:
        net = tmp_path / "net"
        (net / "lo").mkdir(parents=True)
        payload = _run_stats(tmp_path, net, route_dev=None, iterations=1)[0]
        assert (payload["down"], payload["up"]) == ("0B/s", "0B/s")

    def test_missing_route_table_reads_zero_and_survives(self, tmp_path: Path) -> None:
        """No /proc/net/route at all (a locked-down namespace): 0B/s, exit 0,
        nothing on stderr — never a dead feeder."""
        net = _fake_net(tmp_path, wired_up=False)
        payload = _run_stats(
            tmp_path,
            net,
            iterations=1,
            env={"HYPRCONF_STATS_PROC_ROUTE": str(tmp_path / "absent")},
        )[0]
        assert (payload["down"], payload["up"]) == ("0B/s", "0B/s")

    def test_interface_switch_rebases_the_rate_baseline(self, tmp_path: Path) -> None:
        """Ethernet coming up while Wi-Fi held the route: the first eth0
        sample would diff eth0's lifetime counter against wlan0's baseline
        (an absurd one-tick spike, hundreds of GB/s on a real box) unless the
        baseline is rebased to the new interface — that tick must read 0B/s."""
        net = _fake_net(tmp_path, wired_up=False)
        calls = tmp_path / "sleep-calls"
        sleep_body = (
            f'c=0; [[ -r {calls} ]] && read -r c < "{calls}"; c=$((c + 1)); echo $c > "{calls}"\n'
            f'read -r n < "{net}/wlan0/statistics/rx_bytes" && echo $((n + 5000)) > "{net}/wlan0/statistics/rx_bytes"\n'
            f'read -r n < "{net}/wlan0/statistics/tx_bytes" && echo $((n + 1000)) > "{net}/wlan0/statistics/tx_bytes"\n'
            f"if (( c == 2 )); then\n"
            f'    echo 800000000000 > "{net}/eth0/statistics/rx_bytes"\n'
            f'    echo 900000000000 > "{net}/eth0/statistics/tx_bytes"\n'
            f'    echo up > "{net}/eth0/operstate"\n'
            f"fi\n"
        )
        lines = _run_stats(tmp_path, net, iterations=2, sleep_body=sleep_body)
        assert (lines[0]["down"], lines[0]["up"]) == ("5.0kB/s", "1.0kB/s")  # wlan0, steady
        assert (lines[1]["down"], lines[1]["up"]) == ("0B/s", "0B/s")  # eth0's first tick

    def test_vpn_tunnel_default_route_without_gateway(self, tmp_path: Path) -> None:
        """A WireGuard/OpenVPN default route has no gateway hop: Gateway
        00000000 and RTF_UP alone in /proc/net/route (`default dev wg0 scope
        link` to `ip`). The Destination alone selects it — a parse keyed on
        the gateway once froze the rates at 0B/s while the VPN carried all
        traffic.
        """
        net = _fake_net(tmp_path, wired_up=False, wifi=False)
        wg = net / "wg0"
        (wg / "statistics").mkdir(parents=True)
        # Tunnels are virtual: no device/ marker (so the wired-precedence scan
        # must skip it), no wireless/ dir; wg operstate reads "unknown".
        (wg / "operstate").write_text("unknown\n")
        (wg / "statistics" / "rx_bytes").write_text("7000\n")
        (wg / "statistics" / "tx_bytes").write_text("8000\n")
        payload = _run_stats(
            tmp_path,
            net,
            route_dev="wg0",
            route_lines=[_route("wg0", gateway=False, metric=50)],
            iterations=1,
        )[0]
        assert payload["down"] == "5.0kB/s"


# ---------------------------------------------------------------------------
# hyprconf-stats cpu temperature (hwmon, resolved once)
# ---------------------------------------------------------------------------


class TestStatsCpuTemp:
    def _temp(self, tmp_path: Path, sensors: list[tuple[str, str]]) -> str:
        hwmon = _fake_hwmon(tmp_path, sensors)
        net = tmp_path / "net"
        (net / "lo").mkdir(parents=True)
        payload = _run_stats(tmp_path, net, route_dev=None, iterations=1, hwmon_root=hwmon)[0]
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

    def test_sensor_vanishing_mid_stream_blanks_the_cell_and_survives(self, tmp_path: Path) -> None:
        """The stated reason hyprconf-stats shuns `set -e`: a sensor that
        vanishes between ticks must blank its cell, never kill the sampler."""
        hwmon = _fake_hwmon(tmp_path, [("Tctl", "54300")])
        gone = hwmon / "hwmon0" / "temp1_input"
        net = _fake_net(tmp_path, wired_up=False)
        calls = tmp_path / "sleep-calls"
        sleep_body = (
            f'c=0; [[ -r {calls} ]] && read -r c < "{calls}"; c=$((c + 1)); echo $c > "{calls}"\n'
            f'if (( c == 2 )); then rm -f "{gone}"; fi\n'
        )
        lines = _run_stats(tmp_path, net, iterations=2, hwmon_root=hwmon, sleep_body=sleep_body)
        assert lines[0]["temp"] == "54°"
        assert lines[1]["temp"] == ""


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
            ["bash", str(GPU_INFO)],
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

    # -- Intel (xe) -----------------------------------------------------------

    @staticmethod
    def _intel_card(
        drm: Path,
        n: int,
        *,
        media_idle_ms: int | None = None,
        device_id: str | None = "0xb0a0",
        act_freq: str | None = "1200",
        temp: str | None = None,
        runtime_status: str | None = None,
    ) -> Path:
        """Fake xe sysfs for one Intel card: the render/compute GT (gt0-rc)
        with its idle-residency counter, optionally the media GT (gt1-mc) that
        must be ignored, the PCI ids the name is looked up from, hwmon, and
        optionally the PM core's power/runtime_status. Left out by default:
        a card with no runtime_status is assumed awake, so every fixture
        written before the PM gate keeps its behaviour."""
        dev = drm / f"card{n}" / "device"
        rc = dev / "tile0" / "gt0"
        (rc / "gtidle").mkdir(parents=True)
        (rc / "gtidle" / "idle_residency_ms").write_text("0\n")
        (rc / "gtidle" / "name").write_text("gt0-rc\n")
        if act_freq is not None:
            (rc / "freq0").mkdir()
            (rc / "freq0" / "act_freq").write_text(act_freq + "\n")
        if media_idle_ms is not None:
            mc = dev / "tile0" / "gt1" / "gtidle"
            mc.mkdir(parents=True)
            (mc / "idle_residency_ms").write_text(f"{media_idle_ms}\n")
            (mc / "name").write_text("gt1-mc\n")
        (dev / "vendor").write_text("0x8086\n")
        if device_id is not None:
            (dev / "device").write_text(device_id + "\n")
        if temp is not None:
            hw = dev / "hwmon" / "hwmon2"
            hw.mkdir(parents=True)
            (hw / "temp1_input").write_text(temp + "\n")
        if runtime_status is not None:
            pm = dev / "power"
            pm.mkdir(parents=True)
            (pm / "runtime_status").write_text(runtime_status + "\n")
        return dev

    @staticmethod
    def _runtime_status(drm: Path, n: int) -> Path:
        return drm / f"card{n}" / "device" / "power" / "runtime_status"

    @staticmethod
    def _trap(path: Path) -> None:
        """Turn an existing sysfs attribute into a blocking trap: a FIFO with
        no writer. `[[ -r ]]` still passes and the probe still accepts the
        card, but any open() for reading hangs — so a feeder that touches the
        attribute never emits a line and the test times out instead of
        quietly passing on a read that should never have happened."""
        path.unlink()
        os.mkfifo(path)

    @staticmethod
    def _pci_ids(tmp_path: Path) -> Path:
        """A trimmed hwdata pci.ids. Two vendors carry the same device id and
        a subsystem line sits under the wanted one, so a lookup that ignores
        the vendor block, or reads the indented continuation lines, answers
        with the wrong name."""
        ids = tmp_path / "pci.ids"
        ids.write_text(
            "# comment\n"
            "1002  Advanced Micro Devices, Inc. [AMD/ATI]\n"
            "\tb0a0  Not a Panther Lake\n"
            "8086  Intel Corporation\n"
            "\tb080  Panther Lake [Arc B390]\n"
            "\tb0a0  Panther Lake [Intel Graphics]\n"
            "\t\t1849 b0a0  a subsystem line, never the answer\n"
            "C 03  Display controller\n"
            "\t00  VGA compatible controller\n"
        )
        return ids

    @staticmethod
    def _idle_file(drm: Path, n: int, gt: str = "gt0") -> Path:
        return drm / f"card{n}" / "device" / "tile0" / gt / "gtidle" / "idle_residency_ms"

    def _run_intel(
        self,
        tmp_path: Path,
        drm: Path,
        *,
        bumps: list[tuple[Path, int]] | None = None,
    ) -> list[dict]:
        """Run the feeder over `drm` with a fake `sleep` that advances the
        residency counters across the sample window — the same trick the net
        tests play on `ip`, and the only way a static fake tree can express an
        idle GPU (the reading is a delta over the window, not a level)."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        if bumps:
            body = "".join(
                f'read -r n < "{path}"\necho $(( n + {ms} )) > "{path}"\n' for path, ms in bumps
            )
            # command -p runs the real sleep off the standard PATH, never this
            # stub again.
            _write_exe(bin_dir / "sleep", f'#!/usr/bin/env bash\n{body}command -p sleep "$@"\n')
        return self._lines(
            self._run(
                tmp_path,
                nvidia=False,
                drm_root=drm,
                env={
                    "HYPRCONF_GPU_INTERVAL": "0.2",
                    "HYPRCONF_GPU_PCI_IDS": str(self._pci_ids(tmp_path)),
                },
            )
        )

    def test_intel_xe_card_is_named_and_reported(self, tmp_path: Path) -> None:
        """A Panther Lake iGPU: named out of pci.ids, temperature from the
        card's own hwmon, no VRAM of its own (shared), and act_freq in the
        tooltip where NVIDIA puts power draw."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0, temp="47000")
        line = self._run_intel(tmp_path, drm)[0]
        assert line["index"] == 0
        assert line["name"] == "Panther Lake [Intel Graphics]"
        assert line["temp"] == 47
        assert line["vram_total"] == "0"  # the widget renders this as "shared"
        assert line["vram_used"] == "0.0"
        assert line["tooltip"] == (
            "Panther Lake [Intel Graphics] (GPU 0) | Util 100% | Temp 47° "
            "| VRAM shared | Freq 1200MHz"
        )

    def test_amd_refusing_card_reads_idle_and_the_stream_lives(self, tmp_path: Path) -> None:
        """amdgpu answers gpu_busy_percent with -EPERM on a runtime-suspended
        card: the attribute is still 0444 (so the probe and `-r` pass) and
        the read() fails. Unguarded under set -e that killed the whole stream
        — on a hybrid laptop before its first line, which the widget never
        restarts, and the iGPU's reading died with it. A card whose counters
        refuse (here: swapped for directories after the probe, a read error
        for root too) must rank idle, 0/0, and the stream must go on — quietly,
        or the error would repeat into the journal every interval."""
        drm = tmp_path / "drm"
        self._amd_card(drm, 0, busy="5", used=None, total=None, name="Raphael")
        dgpu = self._amd_card(drm, 1, busy="90", used=1024**3, total=8 * 1024**3, name="RX 7700S")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        _write_exe(
            bin_dir / "sleep",
            "#!/usr/bin/env bash\n"
            f'for f in gpu_busy_percent mem_info_vram_used mem_info_vram_total; do [[ -f "{dgpu}/$f" ]] && rm -f "{dgpu}/$f" && mkdir "{dgpu}/$f"; done\n'
            'command -p sleep "$@"\n',
        )
        r = self._run(tmp_path, nvidia=False, drm_root=drm, env={"HYPRCONF_GPU_ITERATIONS": "3"})
        lines = self._lines(r)
        assert r.stderr == ""
        assert [ln["index"] for ln in lines] == [1, 0, 0]  # the dGPU, then the iGPU carries on
        assert lines[0]["util"] == 90
        assert lines[1]["util"] == 5 and lines[1]["tooltip"].endswith("| VRAM shared")

    def test_intel_gt_vanishing_mid_stream_reads_idle_not_pegged(self, tmp_path: Path) -> None:
        """No data must read as idle: a vanished xe residency counter once
        computed a zero idle-delta — a gone GPU pegged at 100% forever, with
        the stream alive so the widget's restart self-heal never ran."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0)
        idle = self._idle_file(drm, 0)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        calls = tmp_path / "sleep-calls"
        _write_exe(
            bin_dir / "sleep",
            f'#!/usr/bin/env bash\nc=0; [[ -r {calls} ]] && read -r c < "{calls}"; c=$((c + 1)); echo $c > "{calls}"\n'
            f'if (( c == 2 )); then rm -f "{idle}"; fi\ncommand -p sleep "$@"\n',
        )
        r = self._run(
            tmp_path,
            nvidia=False,
            drm_root=drm,
            env={
                "HYPRCONF_GPU_INTERVAL": "0.2",
                "HYPRCONF_GPU_PCI_IDS": str(self._pci_ids(tmp_path)),
            },
        )
        assert [ln["util"] for ln in self._lines(r)] == [100, 0]

    def test_intel_busy_gt_never_idles(self, tmp_path: Path) -> None:
        """A residency counter that does not advance means the GT spent none
        of the window idle: 100%."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0)
        assert self._run_intel(tmp_path, drm)[0]["util"] == 100

    def test_intel_idle_gt_reads_zero(self, tmp_path: Path) -> None:
        """Idle for (well past) the whole window: 0%, clamped — the counter
        is millisecond-rounded and can overrun the measured window."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0)
        lines = self._run_intel(tmp_path, drm, bumps=[(self._idle_file(drm, 0), 5000)])
        assert [ln["util"] for ln in lines] == [0, 0]

    def test_intel_partial_idle_lands_between(self, tmp_path: Path) -> None:
        """Half the window idle reads about half busy. The band is wide on
        purpose: the denominator is measured wall-clock, so a loaded runner
        that oversleeps only pushes the figure up."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0)
        line = self._run_intel(tmp_path, drm, bumps=[(self._idle_file(drm, 0), 100)])[0]
        assert 20 <= line["util"] <= 90

    def test_intel_media_gt_is_not_the_reading(self, tmp_path: Path) -> None:
        """gt1-mc (media) idles through a graphics workload, so the reading
        must come from gt0-rc: only the media counter advances here, and the
        answer is still the busy render GT."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0, media_idle_ms=0)
        line = self._run_intel(tmp_path, drm, bumps=[(self._idle_file(drm, 0, "gt1"), 5000)])[0]
        assert line["util"] == 100

    def test_intel_two_cards_follow_the_busier_one(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._intel_card(drm, 0, device_id="0xb080")
        self._intel_card(drm, 1)
        line = self._run_intel(tmp_path, drm, bumps=[(self._idle_file(drm, 0), 5000)])[0]
        assert line["index"] == 1
        assert line["util"] == 100

    def test_intel_unknown_id_no_hwmon_no_freq(self, tmp_path: Path) -> None:
        drm = tmp_path / "drm"
        self._intel_card(drm, 3, device_id="0xffff", act_freq=None)
        line = self._run_intel(tmp_path, drm)[0]
        assert line["name"] == "Intel Graphics"
        assert line["temp"] is None
        assert line["tooltip"] == "Intel Graphics (GPU 3) | Util 100% | Temp n/a | VRAM shared"

    def test_intel_suspended_card_is_never_read_and_ranks_idle(self, tmp_path: Path) -> None:
        """xe resumes the card on every one of the three reads this feeder
        makes: idle_residency_ms_show, act_freq_show and xe_hwmon_read all
        call xe_pm_runtime_get, which tail-calls __pm_runtime_resume(dev, 0)
        (disassembled from the installed xe.ko, kernel 7.1.8-arch1-2-ptl).
        amdgpu's handler returns early instead, so the AMD path's "a
        suspended card just refuses the read" does not transfer. With
        power/runtime_status saying "suspended" none of the three may be
        opened — all three are FIFO traps here, so a feeder that opens one
        blocks and emits nothing — and the card ranks idle rather than
        reading 100% off a counter that is standing still."""
        drm = tmp_path / "drm"
        dev = self._intel_card(drm, 0, temp="47000", runtime_status="suspended")
        self._trap(self._idle_file(drm, 0))
        self._trap(dev / "tile0" / "gt0" / "freq0" / "act_freq")
        self._trap(dev / "hwmon" / "hwmon2" / "temp1_input")
        lines = self._run_intel(tmp_path, drm)
        assert [ln["util"] for ln in lines] == [0, 0]
        assert lines[0]["temp"] is None
        assert lines[0]["tooltip"].endswith("| Temp n/a | VRAM shared")

    def test_intel_resumed_card_re_baselines_instead_of_reading_pegged(
        self, tmp_path: Path
    ) -> None:
        """The counter freezes while the GT is off but the wall clock does
        not, so the first delta after a resume covers a window the card slept
        through — a card that just woke would read 100% busy. The first
        sample after a suspend is a baseline: 0% here, then the genuine 100%
        of a counter that really is not advancing."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0, runtime_status="suspended")
        status = self._runtime_status(drm, 0)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        # The card wakes between the baseline and the first sample; its
        # residency counter is left exactly where it was.
        _write_exe(
            bin_dir / "sleep",
            f'#!/usr/bin/env bash\necho active > "{status}"\ncommand -p sleep "$@"\n',
        )
        lines = self._lines(
            self._run(
                tmp_path,
                nvidia=False,
                drm_root=drm,
                env={
                    "HYPRCONF_GPU_INTERVAL": "0.2",
                    "HYPRCONF_GPU_PCI_IDS": str(self._pci_ids(tmp_path)),
                },
            )
        )
        assert [ln["util"] for ln in lines] == [0, 100]

    def test_intel_active_runtime_status_changes_nothing(self, tmp_path: Path) -> None:
        """The gate is a gate, not a new reading: a card the PM core calls
        active is measured exactly as one with no runtime_status at all."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0, temp="47000", runtime_status="active")
        line = self._run_intel(tmp_path, drm)[0]
        assert line["util"] == 100
        assert line["temp"] == 47
        assert line["tooltip"].endswith("| Temp 47° | VRAM shared | Freq 1200MHz")

    def test_intel_gate_only_skips_a_card_the_pm_core_says_is_down(self, tmp_path: Path) -> None:
        """The gate asks whether the card is DOWN, not whether it is up. An
        allowlist on "active" ranks every status it does not recognise idle
        forever, and `unsupported` is the PM core's word for a device whose
        runtime PM is off — a card that never sleeps, so it must be measured
        (of 400 devices reporting it on the box this was written on, all 400
        had power/runtime_suspended_time 0, against 50 of 50 `suspended` ones
        with a non-zero one). So `unsupported` measures exactly as no file at
        all, while `suspending` — a card on its way down — is still left
        alone: its residency counter is a FIFO trap here, so a read hangs."""
        up = tmp_path / "unsupported"
        up.mkdir()
        self._intel_card(up / "drm", 0, temp="47000", runtime_status="unsupported")
        line = self._run_intel(up, up / "drm")[0]
        assert line["util"] == 100
        assert line["temp"] == 47
        assert line["tooltip"].endswith("| Temp 47° | VRAM shared | Freq 1200MHz")

        down = tmp_path / "suspending"
        down.mkdir()
        self._intel_card(down / "drm", 0, temp="47000", runtime_status="suspending")
        self._trap(self._idle_file(down / "drm", 0))
        line = self._run_intel(down, down / "drm")[0]
        assert line["util"] == 0
        assert line["temp"] is None

    def test_intel_suspended_card_loses_to_an_awake_one(self, tmp_path: Path) -> None:
        """Two cards, the sleeping one first: it ranks idle, so the reading
        follows the card that is actually running something."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0, device_id="0xb080", runtime_status="suspended")
        self._intel_card(drm, 1, runtime_status="active")
        self._trap(self._idle_file(drm, 0))
        line = self._run_intel(tmp_path, drm)[0]
        assert line["index"] == 1
        assert line["util"] == 100

    def test_nvidia_wins_over_an_intel_igpu(self, tmp_path: Path) -> None:
        """A hybrid laptop: the discrete card is the one worth watching, and
        nvidia-smi answers the probe first."""
        drm = tmp_path / "drm"
        self._intel_card(drm, 0)
        line = self._lines(self._run(tmp_path, nvidia=True, drm_root=drm))[0]
        assert line["name"] == "NVIDIA GeForce RTX 5090"

    # -- neither --------------------------------------------------------------

    def test_no_gpu_exits_silently(self, tmp_path: Path) -> None:
        r = self._run(tmp_path, nvidia=False)
        assert r.returncode == 0
        assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# What the READMEs may claim about a tick
# ---------------------------------------------------------------------------

# "forks nothing" and its variants, and the two feeder names, as tokens.
FORK_CLAIM = re.compile(r"forks? nothing|fork-free")
FEEDER_NAME = re.compile(r"hyprconf-(?:stats|gpu-info)")
# Every doc that describes a feeder's tick. The plugin README ships to
# strangers on its own (`omarchy plugin add`), so it is held to the same rule.
TICK_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "CONTRIBUTING.md",
    FEEDERS.parent / "README.md",
)


def test_only_the_stats_feeder_paces_itself_without_a_fork() -> None:
    """The fact the READMEs are held to below, read off the two scripts:
    hyprconf-stats loads bash's `sleep` builtin, so its whole tick is reads
    and integer arithmetic; hyprconf-gpu-info's AMD and Intel loops exec
    /usr/bin/sleep once per interval and load no builtin."""
    stats = STATS.read_text()
    assert 'enable -f "$HYPRCONF_STATS_SLEEP_BUILTIN" sleep' in stats
    gpu = GPU_INFO.read_text()
    assert "enable -f" not in gpu, "the GPU feeder gained a sleep builtin — re-word the READMEs"
    assert len(re.findall(r'^\s*sleep "\$HYPRCONF_GPU_INTERVAL"$', gpu, re.M)) == 2


def test_readmes_never_claim_a_fork_free_tick_for_the_gpu_feeder() -> None:
    """A fork-free tick is hyprconf-stats' property alone, so the feeder
    named last before the claim must be hyprconf-stats — the shape that
    turned false when both names were put in front of one "a tick ... forks
    nothing". The docs ship as the user contract (rule 7) and the plugin
    README ships on its own, so a wrong claim there reaches strangers."""
    for doc in TICK_DOCS:
        text = doc.read_text(encoding="utf-8")
        claims = list(FORK_CLAIM.finditer(text))
        assert claims, f"{doc.name} no longer describes a tick's cost"
        for claim in claims:
            names = FEEDER_NAME.findall(text[: claim.start()])
            assert names and names[-1] == "hyprconf-stats", (
                f"{doc.name}: '{claim.group(0)}' reads as a claim about "
                f"{names[-1] if names else 'both feeders'}"
            )
