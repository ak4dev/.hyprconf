"""The two feeders behind hyprconf.resources, over fake /proc, /sys and PATH
trees: hyprconf-stats (cpu/mem/net/temp) and hyprconf-gpu-info (nvidia-smi
--loop, or a sysfs loop over AMD gpu_busy_percent / Intel xe idle residency)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from conftest import Box

FEEDERS = Path(__file__).parent / "plugin" / "bin"
GPU_INFO = FEEDERS / "hyprconf-gpu-info"
STATS = FEEDERS / "hyprconf-stats"
SLEEP_TAIL = 'command -p sleep "$@"\n'  # the real sleep, never this fake again
# What `enable -f` loads: bash ships it (package bash), and it is the seam's own default.
SLEEP_LOADABLE = Path("/usr/lib/bash/sleep")


def _bump(path: Path, n: int) -> str:
    """Shell that adds `n` to the counter in `path`."""
    return f'read -r v < "{path}"\necho $((v + {n})) > "{path}"\n'


def _tick_body(box: Box, nth: int, cmd: str, every: str = "") -> str:
    """A `sleep` body running `every` each tick and `cmd` on tick `nth`."""
    calls = box.tmp / "sleep-calls"
    return (
        f'c=0; [[ -r {calls} ]] && read -r c < "{calls}"; c=$((c + 1)); echo $c > "{calls}"\n'
        f"{every}if (( c == {nth} )); then {cmd}; fi\n"
    )


# -- hyprconf-stats ---------------------------------------------------------

PROC_STAT = "cpu  100 0 100 800 0 0 0 0 0 0\n"
PROC_MEMINFO = "MemTotal:       33554432 kB\nMemAvailable:   16777216 kB\n"
# /proc/net/route as the kernel prints it (net/ipv4/fib_trie.c,
# fib_route_seq_show): one route of the main table per line, padded to 127.
ROUTE_HEADER = "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT"


def _fake_hwmon(tmp: Path, sensors: list[tuple[str, str]]) -> Path:
    """A fake /sys/class/hwmon: one chip per (label, millidegrees)."""
    root = tmp / "hwmon"
    root.mkdir(exist_ok=True)
    for i, (label, mdeg) in enumerate(sensors):
        chip = root / f"hwmon{i}"
        chip.mkdir()
        (chip / "temp1_label").write_text(label + "\n")
        (chip / "temp1_input").write_text(mdeg + "\n")
    return root


def _fake_net(tmp: Path) -> Path:
    """Fake /sys/class/net: eth0 static, wlan0 the counters the hook advances."""
    net = tmp / "net"
    for name, rx, tx in (("eth0", "1000", "2000"), ("wlan0", "5000", "6000")):
        stats = net / name / "statistics"
        stats.mkdir(parents=True)
        (net / name / "operstate").write_text("up\n")
        (stats / "rx_bytes").write_text(rx + "\n")
        (stats / "tx_bytes").write_text(tx + "\n")
    (net / "lo").mkdir()
    return net


def _route(iface: str, *, gateway: bool = True, metric: int = 600, dest: str = "00000000") -> str:
    """A default route (dest 00000000) through a gateway, or gateway-less."""
    gw, flags = ("0101A8C0", "0003") if gateway else ("00000000", "0001")
    mask = "00000000" if dest == "00000000" else "00FFFFFF"
    return f"{iface}\t{dest}\t{gw}\t{flags}\t0\t0\t{metric}\t{mask}\t0\t0\t0".ljust(127)


def _run_stats(
    box: Box,
    *,
    net: Path | None = None,
    routes: list[str] | None = None,
    iterations: int = 2,
    hwmon: Path | None = None,
    sleep_body: str | None = None,
    env: dict[str, str] | None = None,
    bare_path: bool = False,
) -> list[dict]:
    """N samples, type-pinned; the `sleep` fake advances wlan0 by 5000 rx / 1000
    tx a tick, so 5.0kB/s down + 1.0kB/s up is "read from wlan0" and 0B/s "read
    from any other (static) interface"."""
    net = net or _fake_net(box.tmp)
    wlan = net / "wlan0" / "statistics"
    default = _bump(wlan / "rx_bytes", 5000) + _bump(wlan / "tx_bytes", 1000)
    box.stub("sleep", (sleep_body or default) + SLEEP_TAIL)
    route_f = box.tmp / "proc_net_route"
    lines = [_route("wlan0")] if routes is None else routes
    route_f.write_text("\n".join([ROUTE_HEADER.ljust(127), *lines]) + "\n")
    stat_f = box.tmp / "proc_stat"
    stat_f.write_text(PROC_STAT)
    mem_f = box.tmp / "meminfo"
    mem_f.write_text(PROC_MEMINFO)
    if bare_path:
        # A bare PATH still resolves `bash` (the stub's `env` shebang looks it
        # up there too); an `ip`, `awk` or coreutils call finds nothing.
        bash = shutil.which("bash")
        assert bash, "bash not installed"
        (box.bins / "bash").symlink_to(bash)
    r = box.run(
        STATS,
        env={
            **({"PATH": str(box.bins)} if bare_path else {}),
            "HYPRCONF_STATS_NET_ROOT": str(net),
            "HYPRCONF_STATS_PROC_STAT": str(stat_f),
            "HYPRCONF_STATS_PROC_MEMINFO": str(mem_f),
            "HYPRCONF_STATS_PROC_ROUTE": str(route_f),
            "HYPRCONF_STATS_HWMON_ROOT": str(hwmon or _fake_hwmon(box.tmp, [])),
            # A file that is not there: the PATH stub above is the sleep.
            "HYPRCONF_STATS_SLEEP_BUILTIN": str(box.tmp / "no-loadable-sleep"),
            "HYPRCONF_STATS_INTERVAL": "0",
            "HYPRCONF_STATS_ITERATIONS": str(iterations),
            **(env or {}),
        },
    )
    assert r.returncode == 0, r.stderr
    # A feeder that complains repeats it every tick into the shell's journal.
    assert r.stderr == "", r.stderr
    out = [json.loads(ln) for ln in r.stdout.strip().splitlines()]
    for p in out:  # the contract the widget assigns straight through, unchecked
        assert set(p) == {"cpu", "mem", "down", "up", "temp"}
        assert isinstance(p["cpu"], int)
        assert all(isinstance(p[k], str) for k in ("mem", "down", "up"))
        assert p["temp"] is None or isinstance(p["temp"], int)
    return out


def test_emits_one_sample_per_tick(box: Box) -> None:
    lines = _run_stats(box, iterations=2)
    assert len(lines) == 2
    assert lines[0]["mem"] == "16.0/32.0G"  # MemTotal-MemAvailable, GiB


@pytest.mark.parametrize(
    "routes,down",
    [
        # An eth0 that is up but unrouted (a dock, a tether) is not the reading.
        ([_route("wlan0")], "5.0kB/s"),
        # A gateway-less tunnel route: the Destination alone selects it.
        ([_route("wlan0", gateway=False)], "5.0kB/s"),
        # The kernel keeps a prefix's routes sorted by metric (fib_insert_alias),
        # so the first default wins; neither a link route nor an `unreachable
        # default` ("*", no device) is one.
        (
            [
                _route("wlan0", gateway=False, dest="0001A8C0"),
                _route("*", metric=0),
                _route("eth0", metric=100),
                _route("wlan0", metric=600),
            ],
            "0B/s",  # eth0's static counters
        ),
        ([], "0B/s"),  # no default route at all
    ],
)
def test_rates_come_from_the_default_route_interface(box: Box, routes, down: str) -> None:
    p = _run_stats(box, routes=routes, iterations=1)[0]
    assert (p["down"], p["up"]) == (down, "1.0kB/s" if down != "0B/s" else "0B/s")


def test_a_missing_route_table_reads_zero_and_survives(box: Box) -> None:
    """No /proc/net/route at all (a locked-down namespace): never a dead feeder."""
    p = _run_stats(box, iterations=1, env={"HYPRCONF_STATS_PROC_ROUTE": str(box.tmp / "absent")})[0]
    assert (p["down"], p["up"]) == ("0B/s", "0B/s")


def test_a_tick_execs_nothing(box: Box) -> None:
    """With the stub dir as the whole PATH, a lookup that shells out reads 0B/s."""
    p = _run_stats(box, iterations=1, bare_path=True)[0]
    assert (p["down"], p["up"]) == ("5.0kB/s", "1.0kB/s")


@pytest.mark.skipif(not SLEEP_LOADABLE.is_file(), reason="no bash sleep loadable installed")
def test_the_loadable_sleep_builtin_takes_the_pacing_over(box: Box) -> None:
    """`enable -f` is the last fork a tick would otherwise pay. Pointed at the
    real loadable the seam defaults to, the PATH `sleep` — which every other
    case here paces on, the seam aimed at a file that is not there — is never
    exec'd again."""
    lines = _run_stats(box, iterations=2, env={"HYPRCONF_STATS_SLEEP_BUILTIN": str(SLEEP_LOADABLE)})
    assert len(lines) == 2
    assert "sleep" not in box.commands


def test_an_interface_switch_rebases_the_rate_baseline(box: Box) -> None:
    """Otherwise one sample diffs two unrelated lifetime counters."""
    net = _fake_net(box.tmp)
    route_f = box.tmp / "proc_net_route"
    (net / "eth0/statistics/rx_bytes").write_text("800000000000\n")
    (net / "eth0/statistics/tx_bytes").write_text("900000000000\n")
    wlan = net / "wlan0" / "statistics"
    body = _tick_body(
        box,
        2,
        f'printf %s "$(sed s/wlan0/eth0/ "{route_f}")" > "{route_f}"',
        every=_bump(wlan / "rx_bytes", 5000) + _bump(wlan / "tx_bytes", 1000),
    )
    lines = _run_stats(box, net=net, iterations=2, sleep_body=body)
    assert (lines[0]["down"], lines[0]["up"]) == ("5.0kB/s", "1.0kB/s")  # wlan0, steady
    assert (lines[1]["down"], lines[1]["up"]) == ("0B/s", "0B/s")  # eth0's first tick


@pytest.mark.parametrize(
    "sensors,temp",
    [
        ([("Tdie", "52000"), ("Tctl", "54300")], 54),  # AMD k10temp: Tctl > Tdie
        ([("Core 0", "45000"), ("Package id 0", "47000")], 47),  # Intel: package > core
        ([("Package id 0", "47000"), ("Tctl", "54300")], 54),  # rank, not chip order
        ([("Tctl", "54500")], 55),  # millidegrees rounded
        ([("Composite", "38000"), ("edge", "60000")], None),  # NVMe/GPU chips are not the CPU
        ([], None),  # no hwmon tree at all
    ],
)
def test_the_cpu_sensor_is_the_highest_ranked_label(box: Box, sensors, temp: int | None) -> None:
    assert _run_stats(box, iterations=1, hwmon=_fake_hwmon(box.tmp, sensors))[0]["temp"] == temp


@pytest.mark.parametrize("then", ["", ' && mkdir "$f"'], ids=["vanishing", "refusing"])
def test_a_sensor_vanishing_mid_stream_blanks_the_cell_and_survives(box: Box, then: str) -> None:
    """The stated reason hyprconf-stats shuns `set -e` — and, for a sensor that is
    still there but refuses the read(), the reason the read is quiet: _run_stats
    pins empty stderr, and a complaint here repeats every tick."""
    hwmon = _fake_hwmon(box.tmp, [("Tctl", "54300")])
    body = _tick_body(box, 2, f'f="{hwmon}/hwmon0/temp1_input"; rm -f "$f"{then}')
    assert [ln["temp"] for ln in _run_stats(box, iterations=2, hwmon=hwmon, sleep_body=body)] == [
        54,
        None,
    ]


# -- hyprconf-gpu-info ------------------------------------------------------

GPU_KEYS = {"index", "name", "util", "temp", "vram_used", "vram_total", "tooltip"}

# Two GPUs, two iterations: index 1 is the busy card (the real two-card shape,
# a 3070 idling at 2 MiB beside a working 5090), then the load flips to 0.
NVIDIA_TWO_GPU_LINES = [
    "0, NVIDIA GeForce RTX 3070, 0, 20.11, 31, 2, 8192",
    "1, NVIDIA GeForce RTX 5090, 7, 45.20, 36, 2314, 32607",
    "0, NVIDIA GeForce RTX 3070, 55, 180.00, 62, 6000, 8192",
    "1, NVIDIA GeForce RTX 5090, 1, 30.00, 35, 300, 32607",
]


def _fake_nvidia_smi(count: int, lines: list[str]) -> str:
    """A fake nvidia-smi: the count query prints one line per GPU each holding the total (the real shape), `-l` streams `lines`."""
    count_out = "".join(f"{count}\\n" for _ in range(count))
    stream = "\n".join('        echo "' + ln.replace('"', '\\"') + '"' for ln in lines)
    return f"""\
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


def _pci_ids(tmp: Path) -> Path:
    """A trimmed hwdata pci.ids: two vendors share a device id and a subsystem
    line sits under the wanted one, so a lookup that ignores the vendor block or
    reads the indented continuations answers wrongly."""
    ids = tmp / "pci.ids"
    ids.write_text(
        "# comment\n"
        "1002  Advanced Micro Devices, Inc. [AMD/ATI]\n"
        "\tb0a0  Not a Panther Lake\n"
        "8086  Intel Corporation\n"
        "\tb080  Panther Lake [Arc B390]\n"
        "\tb0a0  Panther Lake [Intel Graphics]\n"
        "\t\t1849 b0a0  a subsystem line, never the answer\n"
    )
    return ids


def _gpu(
    box: Box,
    *,
    nvidia: bool | str = False,
    drm: Path | None = None,
    env: dict[str, str] | None = None,
) -> list[dict]:
    """Over the fake trees, type-pinned; nvidia-smi is always shadowed (a real one must never answer a test)."""
    box.stub(
        "nvidia-smi",
        _fake_nvidia_smi(2, NVIDIA_TWO_GPU_LINES) if nvidia is True else (nvidia or "exit 1\n"),
    )
    r = box.run(
        GPU_INFO,
        env={
            "HYPRCONF_GPU_DRM_ROOT": str(drm or (box.tmp / "drm-empty")),
            "HYPRCONF_GPU_ITERATIONS": "2",
            "HYPRCONF_GPU_INTERVAL": "0",
            "HYPRCONF_GPU_PCI_IDS": str(_pci_ids(box.tmp)),  # never the host's hwdata
            **(env or {}),
        },
    )
    assert r.returncode == 0, r.stderr
    assert r.stderr == "", r.stderr
    out = [json.loads(ln) for ln in r.stdout.strip().splitlines()]
    for p in out:  # the contract the widget assigns straight through, unchecked
        assert set(p) == GPU_KEYS
        assert isinstance(p["index"], int) and isinstance(p["util"], int)
        assert all(isinstance(p[k], str) for k in ("name", "vram_used", "vram_total"))
        assert p["temp"] is None or isinstance(p["temp"], int)
    return out


def test_nvidia_two_gpus_follow_the_busy_card(box: Box) -> None:
    lines = _gpu(box, nvidia=True)
    assert len(lines) == 2  # one JSON line per iteration, not per GPU
    first, second = lines
    assert (first["index"], first["util"], first["temp"]) == (1, 7, 36)
    assert first["name"] == "NVIDIA GeForce RTX 5090"
    assert (first["vram_used"], first["vram_total"]) == ("2.3", "31.8")
    assert first["tooltip"] == (
        "RTX 5090 (GPU 1) | Util 7% | Temp 36° | VRAM 2.3/31.8 GiB | Power 45W"
    )
    assert (second["index"], second["util"], second["temp"]) == (0, 55, 62)  # the load moved
    assert (second["vram_used"], second["vram_total"]) == ("5.9", "8.0")
    assert second["tooltip"].startswith("RTX 3070 (GPU 0)")


def test_nvidia_name_with_comma_parses(box: Box) -> None:
    fake = _fake_nvidia_smi(1, ['0, NVIDIA "Ada", Ltd 4090, 9, 50.0, 40, 1024, 24576'])
    line = _gpu(box, nvidia=fake)[0]
    assert line["name"] == 'NVIDIA "Ada", Ltd 4090'  # quotes escaped, comma kept
    assert (line["util"], line["temp"]) == (9, 40)
    assert (line["vram_used"], line["vram_total"]) == ("1.0", "24.0")


def test_nvidia_memory_tie_broken_by_util_then_index(box: Box) -> None:
    fake = _fake_nvidia_smi(
        2,
        [
            "0, NVIDIA A, 3, 10.0, 30, 500, 8192",
            "1, NVIDIA B, 9, 10.0, 30, 500, 8192",
            "0, NVIDIA A, 9, 10.0, 30, 500, 8192",  # full tie → lowest index
            "1, NVIDIA B, 9, 10.0, 30, 500, 8192",
        ],
    )
    assert [ln["index"] for ln in _gpu(box, nvidia=fake)] == [1, 0]


def test_nvidia_unknown_temp_and_power_are_dropped(box: Box) -> None:
    fake = _fake_nvidia_smi(1, ["0, NVIDIA T, 1, [N/A], [N/A], 100, 8192"])
    line = _gpu(box, nvidia=fake)[0]
    assert line["temp"] is None
    assert line["tooltip"].endswith("| Temp n/a | VRAM 0.1/8.0 GiB")


GiB = 1024**3


def _amd_card(drm: Path, n: int, *, busy: str, temp: str | None = None, **attrs: int | str) -> Path:
    """One AMD card: gpu_busy_percent, optional hwmon, and any of
    mem_info_vram_{used,total} / product_name / vendor / device given."""
    card = drm / f"card{n}" / "device"
    card.mkdir(parents=True)
    (card / "gpu_busy_percent").write_text(busy + "\n")
    for attr, value in attrs.items():
        (card / attr).write_text(f"{value}\n")
    if temp is not None:
        (card / "hwmon" / "hwmon3").mkdir(parents=True)
        (card / "hwmon" / "hwmon3" / "temp1_input").write_text(temp + "\n")
    return card


def test_amd_two_cards_pick_more_vram_used(box: Box) -> None:
    drm = box.tmp / "drm"
    _amd_card(drm, 1, busy="90", temp="50000", mem_info_vram_used=GiB, mem_info_vram_total=16 * GiB)
    _amd_card(
        drm,
        2,
        busy="42",
        temp="61000",
        product_name="RX 7900 XTX",
        mem_info_vram_used=4 * GiB,
        mem_info_vram_total=16 * GiB,
    )
    lines = _gpu(box, drm=drm)
    assert len(lines) == 2  # HYPRCONF_GPU_ITERATIONS bounds the loop
    assert lines[0]["index"] == 2  # more memory used beats a higher busy %
    assert (lines[0]["name"], lines[0]["util"], lines[0]["temp"]) == ("RX 7900 XTX", 42, 61)
    assert lines[0]["tooltip"] == "RX 7900 XTX (GPU 2) | Util 42% | Temp 61° | VRAM 4.0/16.0 GiB"


def test_amd_memory_tie_broken_by_busy_then_index(box: Box) -> None:
    drm = box.tmp / "drm"
    for card, busy in ((1, "10"), (2, "20"), (0, "20")):
        _amd_card(drm, card, busy=busy, mem_info_vram_used=100, mem_info_vram_total=16 * GiB)
    assert _gpu(box, drm=drm)[0]["index"] == 0


@pytest.mark.parametrize(
    "attrs,name,tooltip",
    [
        # No product_name and no PCI id pci.ids knows: "GPU 0" once, never
        # "GPU 0 (GPU 0)"; no hwmon, so no temperature either.
        (
            {"mem_info_vram_used": 2 * GiB, "mem_info_vram_total": 8 * GiB},
            "",
            "GPU 0 | Util 5% | Temp n/a | VRAM 2.0/8.0 GiB",
        ),
        # An APU carries no product_name at all (verified live on a Phoenix
        # iGPU): the name comes from pci.ids, 1002:b0a0 not Intel's b0a0.
        (
            {"vendor": "0x1002", "device": "0xb0a0"},
            "Not a Panther Lake",
            "Not a Panther Lake (GPU 0) | Util 5% | Temp n/a | VRAM shared",
        ),
        # No VRAM files at all: an iGPU carves from system RAM.
        (
            {"product_name": "Raphael"},
            "Raphael",
            "Raphael (GPU 0) | Util 5% | Temp n/a | VRAM shared",
        ),
    ],
)
def test_amd_names_the_card_and_renders_its_vram(box: Box, attrs, name: str, tooltip: str) -> None:
    drm = box.tmp / "drm"
    _amd_card(drm, 0, busy="5", **attrs)
    line = _gpu(box, drm=drm)[0]
    assert (line["name"], line["temp"]) == (name, None)
    assert line["tooltip"] == tooltip
    assert line["vram_total"] == ("8.0" if "GiB" in tooltip else "0")


def test_amd_ignores_connector_nodes(box: Box) -> None:
    """A connector's device/ shares the glob prefix but is not a second GPU."""
    drm = box.tmp / "drm"
    _amd_card(drm, 1, busy="3", mem_info_vram_used=100, mem_info_vram_total=8 * GiB)
    conn = drm / "card1-DP-1" / "device"
    conn.mkdir(parents=True)
    (conn / "gpu_busy_percent").write_text("99\n")
    line = _gpu(box, drm=drm)[0]
    assert (line["index"], line["util"]) == (1, 3)


def test_amd_refusing_temperature_reads_null_quietly(box: Box) -> None:
    """The hwmon read goes through amdgpu's own gate too: a card that refuses it blanks
    the cell without a `read error` line per tick (_gpu pins stderr empty)."""
    drm = box.tmp / "drm"
    temp = _amd_card(drm, 0, busy="5", temp="50000") / "hwmon/hwmon3/temp1_input"
    box.stub("sleep", f'rm -f "{temp}" && mkdir "{temp}"\n' + SLEEP_TAIL)
    assert [ln["temp"] for ln in _gpu(box, drm=drm)] == [50, None]


def test_amd_refusing_card_reads_idle_and_the_stream_lives(box: Box) -> None:
    """amdgpu answers -EPERM on a runtime-suspended card: it ranks idle and the
    stream goes on, quietly. The refusal here is the files swapped for
    directories after the probe — a read error for root too."""
    drm = box.tmp / "drm"
    _amd_card(drm, 0, busy="5", product_name="Raphael")
    dgpu = _amd_card(
        drm,
        1,
        busy="90",
        product_name="RX 7700S",
        mem_info_vram_used=GiB,
        mem_info_vram_total=8 * GiB,
    )
    box.stub(
        "sleep",
        f'for f in gpu_busy_percent mem_info_vram_used mem_info_vram_total; do [[ -f "{dgpu}/$f" ]]'
        f' && rm -f "{dgpu}/$f" && mkdir "{dgpu}/$f"; done\n' + SLEEP_TAIL,
    )
    lines = _gpu(box, drm=drm, env={"HYPRCONF_GPU_ITERATIONS": "3"})
    assert [ln["index"] for ln in lines] == [1, 0, 0]  # the dGPU, then the iGPU carries on
    assert lines[0]["util"] == 90
    assert lines[1]["util"] == 5 and lines[1]["tooltip"].endswith("| VRAM shared")


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
    """One xe card: the render/compute GT (gt0-rc) with its idle-residency
    counter, optionally the media GT (gt1-mc) that must be ignored, the PCI ids,
    hwmon, and power/runtime_status (absent = assumed awake)."""
    dev = drm / f"card{n}" / "device"
    rc = dev / "tile0" / "gt0"
    (rc / "gtidle").mkdir(parents=True)
    (rc / "gtidle" / "idle_residency_ms").write_text("0\n")
    (rc / "gtidle" / "name").write_text("gt0-rc\n")
    (dev / "vendor").write_text("0x8086\n")
    if act_freq is not None:
        (rc / "freq0").mkdir()
        (rc / "freq0" / "act_freq").write_text(act_freq + "\n")
    if media_idle_ms is not None:
        mc = dev / "tile0" / "gt1" / "gtidle"
        mc.mkdir(parents=True)
        (mc / "idle_residency_ms").write_text(f"{media_idle_ms}\n")
        (mc / "name").write_text("gt1-mc\n")
    if device_id is not None:
        (dev / "device").write_text(device_id + "\n")
    if temp is not None:
        (dev / "hwmon" / "hwmon2").mkdir(parents=True)
        (dev / "hwmon" / "hwmon2" / "temp1_input").write_text(temp + "\n")
    if runtime_status is not None:
        (dev / "power").mkdir(parents=True)
        (dev / "power" / "runtime_status").write_text(runtime_status + "\n")
    return dev


def _idle_file(drm: Path, n: int, gt: str = "gt0") -> Path:
    return drm / f"card{n}" / "device" / "tile0" / gt / "gtidle" / "idle_residency_ms"


def _trap(path: Path) -> None:
    """A blocking trap: `[[ -r ]]` passes but any open() hangs, so a feeder that reads the attribute times the test out instead of passing quietly."""
    path.unlink()
    os.mkfifo(path)


def _intel(box: Box, drm: Path, *, bumps: list[tuple[Path, int]] | None = None) -> list[dict]:
    """With a `sleep` that advances residency counters across the window — the only way a static tree expresses an idle GPU."""
    if bumps:
        box.stub("sleep", "".join(_bump(p, ms) for p, ms in bumps) + SLEEP_TAIL)
    return _gpu(box, drm=drm, env={"HYPRCONF_GPU_INTERVAL": "0.2"})


@pytest.mark.parametrize(
    "card,name,tooltip",
    [
        # Named out of pci.ids, temperature from the card's own hwmon, no VRAM
        # of its own (shared), and act_freq where NVIDIA puts power draw.
        (
            {"temp": "47000"},
            "Panther Lake [Intel Graphics]",
            "Panther Lake [Intel Graphics] (GPU 0) | Util 100% | Temp 47° | VRAM shared"
            " | Freq 1200MHz",
        ),
        (
            {"device_id": "0xffff", "act_freq": None},
            "Intel Graphics",
            "Intel Graphics (GPU 0) | Util 100% | Temp n/a | VRAM shared",
        ),
    ],
)
def test_intel_xe_card_is_named_and_reported(box: Box, card, name: str, tooltip: str) -> None:
    drm = box.tmp / "drm"
    _intel_card(drm, 0, **card)
    line = _intel(box, drm)[0]
    assert (line["index"], line["name"]) == (0, name)
    assert (line["vram_used"], line["vram_total"]) == ("0.0", "0")
    assert line["tooltip"] == tooltip


def test_intel_idle_gt_reads_zero(box: Box) -> None:
    """Idle well past the window: 0%, clamped — the counter is ms-rounded."""
    drm = box.tmp / "drm"
    _intel_card(drm, 0)
    assert [ln["util"] for ln in _intel(box, drm, bumps=[(_idle_file(drm, 0), 5000)])] == [0, 0]


def test_intel_partial_idle_lands_between(box: Box) -> None:
    """The band is wide on purpose: the denominator is measured wall-clock."""
    drm = box.tmp / "drm"
    _intel_card(drm, 0)
    assert 20 <= _intel(box, drm, bumps=[(_idle_file(drm, 0), 100)])[0]["util"] <= 90


def test_intel_media_gt_is_not_the_reading(box: Box) -> None:
    """gt1-mc idles through a graphics workload, so gt0-rc is the reading."""
    drm = box.tmp / "drm"
    _intel_card(drm, 0, media_idle_ms=0)
    assert _intel(box, drm, bumps=[(_idle_file(drm, 0, "gt1"), 5000)])[0]["util"] == 100


def test_intel_gt_vanishing_mid_stream_reads_idle_not_pegged(box: Box) -> None:
    """No data must read as idle, never a card pegged at 100%."""
    drm = box.tmp / "drm"
    _intel_card(drm, 0)
    box.stub("sleep", _tick_body(box, 2, f'rm -f "{_idle_file(drm, 0)}"') + SLEEP_TAIL)
    lines = _gpu(box, drm=drm, env={"HYPRCONF_GPU_INTERVAL": "0.2"})
    assert [ln["util"] for ln in lines] == [100, 0]


def test_intel_two_cards_follow_the_busier_one(box: Box) -> None:
    drm = box.tmp / "drm"
    _intel_card(drm, 0, device_id="0xb080")
    _intel_card(drm, 1)
    line = _intel(box, drm, bumps=[(_idle_file(drm, 0), 5000)])[0]
    assert (line["index"], line["util"]) == (1, 100)


# One row per shape of power/runtime_status: absent, a value that is not a known
# one (the test is for being DOWN, not for being up), and the two that are down.
# Every attribute a gated read would touch is a FIFO trap.
@pytest.mark.parametrize(
    "status,traps,util,temp",
    [
        (None, (), 100, 47),
        ("unsupported", (), 100, 47),
        ("suspended", ("idle", "freq", "hwmon"), 0, None),
        ("suspending", ("idle",), 0, None),
    ],
)
def test_intel_pm_gate_only_skips_a_card_the_pm_core_says_is_down(
    box: Box, status: str | None, traps: tuple[str, ...], util: int, temp: int | None
) -> None:
    drm = box.tmp / "drm"
    dev = _intel_card(drm, 0, temp="47000", runtime_status=status)
    for trap in traps:
        _trap(
            {
                "idle": _idle_file(drm, 0),
                "freq": dev / "tile0" / "gt0" / "freq0" / "act_freq",
                "hwmon": dev / "hwmon" / "hwmon2" / "temp1_input",
            }[trap]
        )
    lines = _intel(box, drm)
    assert [ln["util"] for ln in lines] == [util, util]
    assert lines[0]["temp"] == temp
    assert lines[0]["tooltip"].endswith(
        "| Temp 47° | VRAM shared | Freq 1200MHz" if temp else "| Temp n/a | VRAM shared"
    )


def test_intel_resumed_card_re_baselines_instead_of_reading_pegged(box: Box) -> None:
    """The first sample after a resume is a baseline, not a reading."""
    drm = box.tmp / "drm"
    _intel_card(drm, 0, runtime_status="suspended")
    status = drm / "card0" / "device" / "power" / "runtime_status"
    # The card wakes between the baseline and the first sample, its residency
    # counter left exactly where it was.
    box.stub("sleep", f'echo active > "{status}"\n' + SLEEP_TAIL)
    lines = _gpu(box, drm=drm, env={"HYPRCONF_GPU_INTERVAL": "0.2"})
    assert [ln["util"] for ln in lines] == [0, 100]


def test_nvidia_wins_over_an_intel_igpu(box: Box) -> None:
    """A hybrid laptop: the discrete card is the one worth watching."""
    drm = box.tmp / "drm"
    _intel_card(drm, 0)
    assert _gpu(box, nvidia=True, drm=drm)[0]["name"] == "NVIDIA GeForce RTX 5090"


def test_no_gpu_emits_nothing_and_exits_zero(box: Box) -> None:
    """How Service.qml tells dead hardware from a dead stream."""
    assert _gpu(box) == []
