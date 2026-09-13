"""Tests for bin/hyprconf-vulkan-gpu — pinning Vulkan (Steam/Proton under
Xwayland) to the GPU that drives the displays on a dual-GPU box.

The exit codes are the contract the installer reads: 0 nothing to do, 3 at
risk, 1 a usage or read error. A setting already made counts from any of four
places — uwsm's env.d and env, systemd's environment.d, and the live
environment. `use`, `toggle` and `run` must never probe vulkaninfo: `run`
sits on every game launch, and a probe creates a Vulkan instance on every
ICD, waking a runtime-suspended GPU.

HERMETIC: the `box` fixture (conftest.py) plus `gpus()` below — the PCI and
DRM sysfs trees, uwsm's env.d and env and systemd's environment.d are tmp
trees behind their _HYPRCONF_* seams, vulkaninfo is a recording fake, and
the box's environment is built from scratch, so the two variables the tool
looks for cannot leak in from the developer's session. One test points every
seam at an empty tree and checks the tool sees nothing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import Box

REPO_ROOT = Path(__file__).parent.parent.parent
TOOL = REPO_ROOT / "bin" / "hyprconf-vulkan-gpu"

# GPUs as sysfs prints them: vendor/device lowercase 0x-hex, class 0x03xxxx.
NV_3070 = {"addr": "0000:04:00.0", "vendor": "0x10de", "device": "0x2484", "connected": 0}
NV_5090 = {"addr": "0000:0a:00.0", "vendor": "0x10de", "device": "0x2b85", "connected": 2}
AMD_7900 = {"addr": "0000:03:00.0", "vendor": "0x1002", "device": "0x744c", "connected": 0}
AMD_7900_DISPLAY = {**AMD_7900, "addr": "0000:0c:00.0", "connected": 1}
INTEL_IGPU = {"addr": "0000:00:02.0", "vendor": "0x8086", "device": "0xa780", "connected": 0}

LOADER_LINES = [
    "export VK_LOADER_DEVICE_ID_FILTER=0x2b85",
    "export VK_LOADER_DEVICE_SELECT=10de:2b85",
]
NV_LINES = [
    "export __NV_PRIME_RENDER_OFFLOAD=1",
    "export __VK_LAYER_NV_optimus=NVIDIA_only",
]
FIX_LINES = LOADER_LINES + NV_LINES
ALT_LINES = ["export PROTON_ENABLE_WAYLAND=1"]
# The tool's own env.d file, under the seams.
ENV_NAME = "50-hyprconf-vulkan-gpu"


def vulkaninfo_summary(*gpus: dict) -> str:
    """`vulkaninfo --summary`'s Devices section, GPU0 first (vulkan-tools 1.4)."""
    out = "==========\nVULKANINFO\n==========\n\nDevices:\n========\n"
    for i, g in enumerate(gpus):
        out += (
            f"GPU{i}:\n\tapiVersion         = 1.4.312\n"
            f"\tvendorID           = {g['vendor']}\n\tdeviceID           = {g['device']}\n"
            "\tdeviceType         = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU\n"
        )
    return out


def gpus(box: Box, *cards: dict) -> Box:
    """Give the box a fake sysfs for `cards` — a PCI directory per GPU with
    class/vendor/device, a DRM card<N> linking to it, and one connected
    connector per requested output plus one disconnected — and point the
    tool's seams at it. A non-GPU PCI device and a non-GPU card go in too:
    both must be ignored."""
    pci, drm = box.tmp / "sys-pci", box.tmp / "sys-drm"
    for d in (pci, drm):
        d.mkdir()
    for n, g in enumerate(cards, start=1):
        dev = pci / g["addr"]
        dev.mkdir()
        (dev / "class").write_text("0x030000\n")
        (dev / "vendor").write_text(g["vendor"] + "\n")
        (dev / "device").write_text(g["device"] + "\n")
        card = drm / f"card{n}"
        card.mkdir()
        (card / "device").symlink_to(dev)
        for k in range(g["connected"] + 1):
            conn = drm / f"card{n}-DP-{k + 1}"
            conn.mkdir()
            (conn / "status").write_text("connected\n" if k < g["connected"] else "disconnected\n")
    nic = pci / "0000:06:00.0"
    nic.mkdir()
    (nic / "class").write_text("0x020000\n")
    (nic / "vendor").write_text("0x8086\n")
    (nic / "device").write_text("0x15f3\n")
    box.env.update(
        {
            "_HYPRCONF_SYS_PCI": str(pci),
            "_HYPRCONF_SYS_DRM": str(drm),
            # An absolute name: found only while this box's fake exists, never
            # the real vulkaninfo (nor the shared fake behind it on PATH).
            "_HYPRCONF_VULKANINFO": str(box.bins / "vulkaninfo"),
            "_HYPRCONF_UWSM_ENV_D": str(env_file(box).parent),
            "_HYPRCONF_UWSM_ENV": str(box.home / ".config" / "uwsm" / "env"),
            "_HYPRCONF_ENVIRONMENT_D": str(box.home / ".config" / "environment.d"),
            "FAKE_VULKANINFO": str(box.tmp / "vulkaninfo-summary"),
        }
    )
    return box


def run(box: Box, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return box.run(TOOL, *args, **kwargs)


def vulkaninfo(box: Box, summary: str | None) -> None:
    """A recording vulkaninfo printing `summary`; None: one that fails (no ICD)."""
    if summary is None:
        box.stub("vulkaninfo", "echo 'ERROR: [Loader Message] no ICD' >&2\nexit 1\n")
        return
    (box.tmp / "vulkaninfo-summary").write_text(summary)
    box.stub("vulkaninfo", '[[ $1 == --summary ]] && cat "$FAKE_VULKANINFO"\n')


def env_file(box: Box) -> Path:
    return box.home / ".config" / "uwsm" / "env.d" / ENV_NAME


@pytest.fixture
def dual(box: Box) -> Box:
    """Two NVIDIA GPUs, the displays on the second by PCI order: the failing case."""
    return gpus(box, NV_3070, NV_5090)


def exports(path: Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines() if ln.startswith("export ")]


def sourced(path: Path, *names: str) -> list[str]:
    """What `sh` sees after sourcing the file, one value per name."""
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh not installed")
    subprocess.run([sh, "-n", str(path)], check=True)
    probe = " ".join(f'"${n}"' for n in names)
    r = subprocess.run(
        [sh, "-c", f". \"$1\"; printf '%s\\n' {probe}", "sh", str(path)],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ["PATH"]},
    )
    return r.stdout.splitlines()


# ---------------------------------------------------------------------------
# status: the diagnosis
# ---------------------------------------------------------------------------


def test_single_gpu_nothing_to_do(box: Box) -> None:
    gpus(box, NV_5090)
    r = run(box, "status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0000:0a:00.0  10de:2b85  NVIDIA  connected outputs: 2" in r.stdout
    assert "nothing to do — 1 GPU" in r.stdout


def test_display_on_second_gpu_is_at_risk(dual: Box) -> None:
    r = run(dual, "status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "0000:04:00.0  10de:2484  NVIDIA  connected outputs: 0" in r.stdout
    assert "0000:0a:00.0  10de:2b85  NVIDIA  connected outputs: 2" in r.stdout
    assert "display GPU:      0000:0a:00.0 (10de:2b85)" in r.stdout
    assert "Vulkan device 0:  10de:2484 (assumed PCI order; vulkaninfo not found)" in r.stdout
    assert "configured:       no" in r.stdout
    assert "AT RISK" in r.stdout and "hyprconf-vulkan-gpu fix" in r.stdout
    q = run(dual, "status", "--quiet")
    assert q.returncode == 3 and q.stdout == "" and q.stderr == ""


def test_displays_on_first_gpu_nothing_to_do(box: Box) -> None:
    gpus(box, {**NV_3070, "connected": 1}, {**NV_5090, "connected": 0})
    r = run(box, "status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "display GPU:      0000:04:00.0 (10de:2484)" in r.stdout
    assert "the display GPU is Vulkan device 0" in r.stdout
    assert run(box, "status", "--quiet").returncode == 0


@pytest.mark.parametrize(
    ("first_connected", "winner", "rc"),
    [(1, "0000:0a:00.0 (10de:2b85)", 3), (2, "0000:04:00.0 (10de:2484)", 0)],
    ids=["most-wins", "tie-lowest-address"],
)
def test_most_connected_outputs_wins_and_is_said(
    box: Box, first_connected: int, winner: str, rc: int
) -> None:
    # NV_5090 has two connected outputs: 1 loses to it, 2 ties and the lower
    # PCI address (the first GPU, Vulkan device 0 by PCI order) is picked.
    gpus(box, {**NV_3070, "connected": first_connected}, NV_5090)
    r = run(box, "status")
    assert r.returncode == rc, r.stdout + r.stderr
    assert (
        f"display GPU:      {winner} — several GPUs have outputs; "
        "most connected wins, tie -> lowest PCI address" in r.stdout
    )


def test_no_connected_output_nothing_to_pin(box: Box) -> None:
    gpus(box, NV_3070, {**NV_5090, "connected": 0})
    r = run(box, "status")
    assert r.returncode == 0
    assert "display GPU:      none" in r.stdout and "nothing to pin" in r.stdout
    f = run(box, "fix")
    assert f.returncode == 1 and "cannot tell which one to pin" in f.stderr


def test_vulkaninfo_order_beats_pci_order(dual: Box) -> None:
    vulkaninfo(dual, vulkaninfo_summary(NV_5090, NV_3070))
    r = run(dual, "status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Vulkan device 0:  10de:2b85 (vulkaninfo GPU0)" in r.stdout
    assert "the display GPU is Vulkan device 0" in r.stdout


def test_vulkaninfo_confirms_the_risk(box: Box) -> None:
    # PCI order would clear this box (displays on the first GPU); vulkaninfo says otherwise.
    gpus(box, {**NV_3070, "connected": 1}, {**NV_5090, "connected": 0})
    vulkaninfo(box, vulkaninfo_summary(NV_5090, NV_3070))
    r = run(box, "status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Vulkan device 0:  10de:2b85 (vulkaninfo GPU0)" in r.stdout


def test_vulkaninfo_uppercase_ids_are_matched(dual: Box) -> None:
    vulkaninfo(dual, vulkaninfo_summary({**NV_5090, "device": "0x2B85"}, NV_3070))
    assert run(dual, "status", "--quiet").returncode == 0


def test_a_failing_vulkaninfo_is_not_reported_as_absent(dual: Box) -> None:
    # vulkan-tools installed but no usable ICD: the fallback says so, rather
    # than sending the user to install what they already have.
    vulkaninfo(dual, None)
    r = run(dual, "status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Vulkan device 0:  10de:2484 (assumed PCI order; vulkaninfo gave no GPU0)" in r.stdout
    assert "not found" not in r.stdout


def test_reads_nothing_outside_the_seams(box: Box) -> None:
    """Every seam at an empty tree: the tool must find no GPU and no config —
    whatever the real box has."""
    gpus(box)
    r = run(box, "status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"none under {box.env['_HYPRCONF_SYS_PCI']}" in r.stdout
    assert "display GPU:      none" in r.stdout
    assert "Vulkan device 0:  unknown" in r.stdout
    assert "configured:       no" in r.stdout
    assert "nothing to do — 0 GPU" in r.stdout


@pytest.mark.parametrize("sub", ["status", "fix"])
def test_unreadable_sysfs_is_an_error(dual: Box, sub: str) -> None:
    """A seam at a file, not a tree: exit 1 (install.sh turns it into a
    warning), nothing written, nothing asked. One `[[ -d && -d ]]` covers both
    seams, so breaking either one is the same test."""
    broken = dual.tmp / "not-a-sysfs"
    broken.write_text("")
    r = run(dual, sub, tty=True, env={"_HYPRCONF_SYS_PCI": str(broken)})
    assert r.returncode == 1, r.stdout + r.stderr
    assert "hyprconf-vulkan-gpu: cannot read sysfs" in r.stderr and str(broken) in r.stderr
    assert r.stdout == "" and dual.files() == set()


# ---------------------------------------------------------------------------
# already configured
# ---------------------------------------------------------------------------


def _configured(box: Box, where: str) -> tuple[str, dict[str, str]]:
    """Plant an existing configuration; returns (what status must mention, env extra)."""
    cfg = box.home / ".config"
    if where == "environment.d":
        f = cfg / "environment.d" / "50-vulkan-primary-gpu.conf"
        f.parent.mkdir(parents=True)
        f.write_text(
            "# hand-written\nVK_LOADER_DEVICE_ID_FILTER=0x2b85\nVK_LOADER_DEVICE_SELECT=10de:2b85\n"
        )
        return f"VK_LOADER_DEVICE_ID_FILTER in {f}", {}
    if where == "uwsm/env.d":
        f = cfg / "uwsm" / "env.d" / "10-mine"
        f.parent.mkdir(parents=True)
        f.write_text("export FOO=1\n  export PROTON_ENABLE_WAYLAND=1\n")
        return f"PROTON_ENABLE_WAYLAND in {f}", {}
    if where == "uwsm/env":
        f = cfg / "uwsm" / "env"
        f.parent.mkdir(parents=True)
        f.write_text("export VK_LOADER_DEVICE_ID_FILTER=0x2b85\n")
        return f"VK_LOADER_DEVICE_ID_FILTER in {f}", {}
    assert where == "live"
    return "VK_LOADER_DEVICE_ID_FILTER in the live environment", {
        "VK_LOADER_DEVICE_ID_FILTER": "0x2b85"
    }


@pytest.mark.parametrize("where", ["environment.d", "uwsm/env.d", "uwsm/env", "live"])
def test_already_configured_is_reported(dual: Box, where: str) -> None:
    mention, extra = _configured(dual, where)
    before = dual.files()
    r = run(dual, "status", env=extra)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"configured:       {mention}" in r.stdout
    assert "already configured" in r.stdout
    assert dual.files() == before


def test_commented_lines_do_not_count(dual: Box) -> None:
    f = dual.home / ".config" / "environment.d" / "old.conf"
    f.parent.mkdir(parents=True)
    f.write_text("# VK_LOADER_DEVICE_ID_FILTER=0x2b85\n#export PROTON_ENABLE_WAYLAND=1\n")
    r = run(dual, "status")
    assert r.returncode == 3 and "configured:       no" in r.stdout


# ---------------------------------------------------------------------------
# fix / alt / remove
# ---------------------------------------------------------------------------


def test_fix_writes_the_four_lines_for_the_display_gpu(dual: Box) -> None:
    r = run(dual, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(dual)) == FIX_LINES
    head = env_file(dual).read_text().splitlines()[:2]
    assert all(ln.startswith("#") for ln in head)
    assert (
        "0000:0a:00.0 (NVIDIA 10de:2b85)" in head[0]
        and "0000:04:00.0 (NVIDIA 10de:2484)" in head[1]
    )
    assert f"wrote {env_file(dual)}" in r.stdout and "re-login to apply" in r.stdout
    assert sourced(
        env_file(dual),
        "VK_LOADER_DEVICE_ID_FILTER",
        "VK_LOADER_DEVICE_SELECT",
        "__NV_PRIME_RENDER_OFFLOAD",
        "__VK_LAYER_NV_optimus",
    ) == ["0x2b85", "10de:2b85", "1", "NVIDIA_only"]
    assert dual.files() == {env_file(dual)}
    s = run(dual, "status")
    assert s.returncode == 0 and f"VK_LOADER_DEVICE_ID_FILTER in {env_file(dual)}" in s.stdout


def test_amd_display_gpu_gets_loader_lines_only(box: Box) -> None:
    gpus(box, NV_3070, AMD_7900_DISPLAY)
    r = run(box, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(box)) == [
        "export VK_LOADER_DEVICE_ID_FILTER=0x744c",
        "export VK_LOADER_DEVICE_SELECT=1002:744c",
    ]
    assert "(AMD 1002:744c)" in env_file(box).read_text()


def test_first_nvidia_gpu_behind_amd_gets_no_nv_pair(box: Box) -> None:
    gpus(box, AMD_7900, NV_5090)
    r = run(box, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(box)) == LOADER_LINES


def test_nv_pair_needs_an_nvidia_gpu_ahead_in_pci_order(box: Box) -> None:
    # NVIDIA display GPU first, another NVIDIA GPU behind it: nothing to fix,
    # but a forced fix must not add the pair (the driver's GPU 0 is the display GPU).
    gpus(box, {**NV_5090, "addr": "0000:01:00.0"}, {**NV_3070, "connected": 0})
    assert run(box, "status", "--quiet").returncode == 0
    r = run(box, "fix")
    assert r.returncode == 0 and exports(env_file(box)) == LOADER_LINES


def test_three_gpus_names_every_hidden_one(box: Box) -> None:
    gpus(box, INTEL_IGPU, NV_3070, NV_5090)
    r = run(box, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(box)) == FIX_LINES
    assert (
        "0000:00:02.0 (Intel 8086:a780), 0000:04:00.0 (NVIDIA 10de:2484)"
        in env_file(box).read_text()
    )


def test_fix_is_idempotent(dual: Box) -> None:
    assert run(dual, "fix").returncode == 0
    content = env_file(dual).read_bytes()
    old = 1_600_000_000
    os.utime(env_file(dual), (old, old))
    r = run(dual, "fix")
    assert r.returncode == 0 and "already current" in r.stdout and "wrote" not in r.stdout
    assert env_file(dual).read_bytes() == content
    assert env_file(dual).stat().st_mtime == old


def test_fix_refuses_on_a_single_gpu_box(box: Box) -> None:
    gpus(box, NV_5090)
    r = run(box, "fix")
    assert r.returncode == 1 and "single-GPU" in r.stderr and box.files() == set()


def test_alt_writes_proton_wayland_only(dual: Box) -> None:
    r = run(dual, "alt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(dual)) == ALT_LINES
    assert env_file(dual).read_text().startswith("# hyprconf-vulkan-gpu:")
    assert sourced(env_file(dual), "PROTON_ENABLE_WAYLAND", "VK_LOADER_DEVICE_ID_FILTER") == [
        "1",
        "",
    ]
    assert "re-login to apply" in r.stdout
    again = run(dual, "alt")
    assert again.returncode == 0 and "already current" in again.stdout
    s = run(dual, "status")
    assert s.returncode == 0 and f"PROTON_ENABLE_WAYLAND in {env_file(dual)}" in s.stdout


def test_remove_deletes_the_env_file(dual: Box) -> None:
    assert run(dual, "fix").returncode == 0
    r = run(dual, "remove")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"removed {env_file(dual)}" in r.stdout
    assert dual.files() == set()
    again = run(dual, "remove")
    assert again.returncode == 0 and "nothing to remove" in again.stdout


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["help", "-h", "--help"])
def test_help(dual: Box, arg: str) -> None:
    r = run(dual, arg)
    assert r.returncode == 0
    for sub in (
        "status [--quiet]",
        "fix",
        "use <gpu>",
        "toggle",
        "run <gpu>",
        "alt",
        "remove",
    ):
        assert f"hyprconf-vulkan-gpu {sub}" in r.stdout
    for seam in (
        "_HYPRCONF_SYS_PCI",
        "_HYPRCONF_SYS_DRM",
        "_HYPRCONF_VULKANINFO",
        "_HYPRCONF_UWSM_ENV_D",
        "_HYPRCONF_UWSM_ENV",
        "_HYPRCONF_ENVIRONMENT_D",
    ):
        assert seam in r.stdout
    assert "RandR" in r.stdout and "VK_LOADER_DEVICE_ID_FILTER" in r.stdout


def test_unknown_subcommand(dual: Box) -> None:
    r = run(dual, "bogus")
    assert r.returncode == 1 and "unknown subcommand: bogus" in r.stderr


# ---------------------------------------------------------------------------
# use / toggle / run: choosing a GPU, and switching between them
# ---------------------------------------------------------------------------

# The `dual` box has the displays on the second GPU, so "other" is the 3070 —
# which is also the NVIDIA driver's own GPU 0, hence never the PRIME pair.
LOADER_LINES_3070 = [
    "export VK_LOADER_DEVICE_ID_FILTER=0x2484",
    "export VK_LOADER_DEVICE_SELECT=10de:2484",
]


def test_use_display_writes_what_fix_writes(dual: Box) -> None:
    assert run(dual, "use", "display").returncode == 0
    assert exports(env_file(dual)) == FIX_LINES


def test_use_other_pins_the_non_display_gpu_without_the_nv_pair(dual: Box) -> None:
    r = run(dual, "use", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(dual)) == LOADER_LINES_3070
    head = env_file(dual).read_text().splitlines()[:2]
    assert "0000:04:00.0 (NVIDIA 10de:2484)" in head[0]
    assert "0000:0a:00.0 (NVIDIA 10de:2b85)" in head[1]
    assert sourced(env_file(dual), "VK_LOADER_DEVICE_SELECT", "__NV_PRIME_RENDER_OFFLOAD") == [
        "10de:2484",
        "",
    ]


@pytest.mark.parametrize("selector", ["0", "0000:04:00.0", "04:00.0", "10de:2484"])
def test_use_accepts_index_address_long_or_short_and_id(dual: Box, selector: str) -> None:
    assert run(dual, "use", selector).returncode == 0
    assert exports(env_file(dual)) == LOADER_LINES_3070


def test_use_rejects_an_unknown_selector_and_writes_nothing(dual: Box) -> None:
    r = run(dual, "use", "nope")
    assert r.returncode == 1 and "no GPU matches 'nope'" in r.stderr
    assert dual.files() == set()


def test_use_without_a_selector_is_a_usage_error(dual: Box) -> None:
    r = run(dual, "use")
    assert r.returncode == 1 and "usage: hyprconf-vulkan-gpu use" in r.stderr


def test_use_refuses_on_a_single_gpu_box(box: Box) -> None:
    gpus(box, NV_5090)
    r = run(box, "use", "display")
    assert r.returncode == 1 and "nothing to pin on a single-GPU box" in r.stderr


def test_toggle_starts_from_the_display_gpu_then_swaps_back(dual: Box) -> None:
    first = run(dual, "toggle")
    assert first.returncode == 0, first.stdout + first.stderr
    assert exports(env_file(dual)) == LOADER_LINES_3070
    assert "0000:0a:00.0 (10de:2b85) -> 0000:04:00.0 (10de:2484)" in first.stdout
    second = run(dual, "toggle")
    assert second.returncode == 0, second.stdout + second.stderr
    assert exports(env_file(dual)) == FIX_LINES
    assert "0000:04:00.0 (10de:2484) -> 0000:0a:00.0 (10de:2b85)" in second.stdout


def test_toggle_refuses_on_a_single_gpu_box(box: Box) -> None:
    gpus(box, NV_5090)
    r = run(box, "toggle")
    assert r.returncode == 1 and "nothing to toggle on a single-GPU box" in r.stderr


@pytest.mark.parametrize("args", [("use", "other"), ("toggle",)])
def test_use_and_toggle_name_a_setting_outside_their_own_file(dual: Box, args: tuple) -> None:
    stray = dual.home / ".config" / "environment.d" / "50-mine.conf"
    stray.parent.mkdir(parents=True)
    stray.write_text("VK_LOADER_DEVICE_ID_FILTER=0x2b85\n")
    r = run(dual, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "also set outside" in r.stdout and str(stray) in r.stdout
    assert exports(env_file(dual)) == LOADER_LINES_3070


def test_run_sets_the_variables_for_one_command_and_writes_nothing(dual: Box) -> None:
    r = run(dual, "run", "display", "--", "env")
    assert r.returncode == 0, r.stdout + r.stderr
    seen = dict(ln.split("=", 1) for ln in r.stdout.splitlines() if "=" in ln)
    assert seen["VK_LOADER_DEVICE_ID_FILTER"] == "0x2b85"
    assert seen["VK_LOADER_DEVICE_SELECT"] == "10de:2b85"
    assert seen["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert seen["__VK_LAYER_NV_optimus"] == "NVIDIA_only"
    assert dual.files() == set()


def test_run_clears_an_nv_pair_the_target_must_not_have(dual: Box) -> None:
    """A session pinned to the second GPU exports the pair; a `run` at the
    first must not inherit it, or the driver offloads with nowhere to go."""
    r = run(
        dual,
        "run",
        "other",
        "--",
        "env",
        env={"__NV_PRIME_RENDER_OFFLOAD": "1", "__VK_LAYER_NV_optimus": "NVIDIA_only"},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VK_LOADER_DEVICE_SELECT=10de:2484" in r.stdout
    assert "__NV_PRIME_RENDER_OFFLOAD" not in r.stdout
    assert "__VK_LAYER_NV_optimus" not in r.stdout


def test_run_takes_the_command_without_a_double_dash(dual: Box) -> None:
    r = run(dual, "run", "display", "env")
    assert r.returncode == 0 and "VK_LOADER_DEVICE_SELECT=10de:2b85" in r.stdout


def test_run_without_a_command_is_a_usage_error(dual: Box) -> None:
    r = run(dual, "run", "display")
    assert r.returncode == 1 and "no command given" in r.stderr


# Two cards with the same vendor:device: the loader's id filter cannot tell
# them apart, so every id-keyed promise must refuse instead of lying.
NV_3070_TWIN = {**NV_3070, "addr": "0000:0b:00.0", "connected": 2}


@pytest.fixture
def twins(box: Box) -> Box:
    """Two identical NVIDIA cards, the displays on the second."""
    return gpus(box, NV_3070, NV_3070_TWIN)


@pytest.mark.parametrize("args", [("fix",), ("use", "display"), ("use", "1"), ("toggle",)])
def test_identical_gpu_ids_refuse_to_write_a_pin(twins: Box, args: tuple) -> None:
    r = run(twins, *args)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "sharing id 10de:2484" in r.stderr and "cannot separate identical cards" in r.stderr
    assert not env_file(twins).exists()


def test_identical_gpu_ids_refuse_to_run(twins: Box) -> None:
    r = run(twins, "run", "display", "--", "env")
    assert r.returncode == 1 and "sharing id 10de:2484" in r.stderr


def test_identical_gpu_ids_status_says_cannot_tell(twins: Box) -> None:
    r = run(twins, "status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "cannot tell — two GPUs share id 10de:2484" in r.stdout


def test_no_arg_subcommands_reject_leftover_arguments(dual: Box) -> None:
    """`toggle other` must die pointing at `use`, never silently plain-toggle."""
    r = run(dual, "toggle", "other")
    assert r.returncode == 1
    assert "toggle takes no arguments (did you mean: use other?)" in r.stderr
    assert not env_file(dual).exists()
    for cmd in ("fix", "alt", "remove"):
        r = run(dual, cmd, "stray")
        assert r.returncode == 1 and f"{cmd} takes no arguments" in r.stderr, cmd


def test_use_toggle_run_never_probe_vulkan(dual: Box) -> None:
    """`run` sits on every game launch: probing every ICD there would wake a
    runtime-suspended GPU. Only status and fix may pay for vulkaninfo."""
    vulkaninfo(dual, vulkaninfo_summary(NV_3070, NV_5090))
    for args in (("use", "other"), ("toggle",), ("run", "other", "--", "true")):
        dual.reset()
        r = run(dual, *args)
        assert r.returncode == 0, (args, r.stdout + r.stderr)
        assert dual.calls_of("vulkaninfo") == [], args
