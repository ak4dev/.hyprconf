"""Tests for bin/hyprconf-vulkan-gpu — pinning Vulkan (Steam/Proton under
Xwayland) to the GPU that drives the displays on a dual-GPU box.

Verifies:
- the diagnosis from sysfs: GPUs by PCI class, the display GPU by connected
  connectors (most wins), Vulkan device 0 from vulkaninfo when present and
  assumed PCI order otherwise, and the exit codes (0 nothing to do, 3 at risk)
- `fix` writes the uwsm env.d file with exactly the loader lines for the
  display GPU, the NVIDIA pair only for an NVIDIA display GPU behind another
  NVIDIA GPU, sh-clean and yielding those variables when sourced; idempotent
  (bytes and mtime); refuses on a single-GPU box
- `use` pins a GPU you name (display / other / index / PCI address, long or
  short / vendor:device) and `toggle` swaps to the next in PCI order, both
  deriving the NVIDIA pair from the target rather than the display GPU, and
  both naming a VK_LOADER_*/PROTON_ENABLE_WAYLAND line set outside their file
- `run` sets one GPU's variables for a single command, writes nothing, and
  clears an NVIDIA pair the target must not have
- two cards sharing a vendor:device id refuse every id-keyed promise (the
  loader cannot separate them); no-arg subcommands reject leftover arguments;
  use/toggle/run never probe vulkaninfo (run sits on every game launch)
- "already configured" in environment.d/*.conf, uwsm/env.d/*, uwsm/env and
  the live environment silences status and prompt
- `prompt`: silent when nothing is at risk or the ignore marker exists, one
  info line and no gum without a terminal or inside omarchy-update (its
  OMARCHY_UPDATE_LOGGED marker; script(1) gives the hook's run a pty), gum's
  three Fix/Alt/Ignore options applied when there is one; `alt`, `ignore`,
  `remove`, `help`

HERMETIC: every path the tool reads — the PCI and DRM sysfs trees, uwsm's
env.d and env, systemd's environment.d, the state dir — is a tmp tree behind
its _HYPRCONF_* seam, HOME is relocated, gum and vulkaninfo are recording
fakes, and the two variables the tool looks for are stripped from the live
environment before every run. The real sysfs and HOME are never read: one
test points every seam at an empty tree and checks the tool sees nothing.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

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
# The tool's own file and marker, under the seams.
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


class Box:
    """A throwaway box: fake sysfs for the given GPUs (PCI dirs with class/
    vendor/device, DRM card<N> linking to its PCI dir, one connected
    connector per requested output plus one disconnected), a relocated HOME,
    a recording gum fake, optionally a vulkaninfo fake."""

    def __init__(self, tmp: Path, gpus: list[dict]) -> None:
        self.tmp = tmp
        self.home = tmp / "home"
        self.bins = tmp / "bins"
        self.pci = tmp / "sys-pci"
        self.drm = tmp / "sys-drm"
        self.calls_file = tmp / "calls.txt"
        self.answer = tmp / "gum-answer"
        for d in (self.home, self.bins, self.pci, self.drm):
            d.mkdir()
        for n, g in enumerate(gpus, start=1):
            dev = self.pci / g["addr"]
            dev.mkdir()
            (dev / "class").write_text("0x030000\n")
            (dev / "vendor").write_text(g["vendor"] + "\n")
            (dev / "device").write_text(g["device"] + "\n")
            card = self.drm / f"card{n}"
            card.mkdir()
            (card / "device").symlink_to(dev)
            for k in range(g["connected"] + 1):
                conn = self.drm / f"card{n}-DP-{k + 1}"
                conn.mkdir()
                (conn / "status").write_text(
                    "connected\n" if k < g["connected"] else "disconnected\n"
                )
        # A non-GPU PCI device and a non-GPU card: both must be ignored.
        nic = self.pci / "0000:06:00.0"
        nic.mkdir()
        (nic / "class").write_text("0x020000\n")
        (nic / "vendor").write_text("0x8086\n")
        (nic / "device").write_text("0x15f3\n")
        self._fake(
            "gum",
            "IFS=$'\\t'; printf '%s\\n' \"gum${IFS}$*\" >> \"$FAKE_CALLS\"\n"
            '[[ -r $FAKE_GUM_ANSWER ]] || exit 1\ncat "$FAKE_GUM_ANSWER"\n',
        )

    def _fake(self, name: str, body: str) -> None:
        fake = self.bins / name
        fake.write_text("#!/usr/bin/env bash\n" + body)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def vulkaninfo(self, summary: str | None) -> None:
        """A vulkaninfo printing `summary`; None: one that fails (no ICD)."""
        if summary is None:
            self._fake("vulkaninfo", "echo 'ERROR: [Loader Message] no ICD' >&2\nexit 1\n")
            return
        (self.tmp / "vulkaninfo-summary").write_text(summary)
        self._fake("vulkaninfo", '[[ $1 == --summary ]] && cat "$FAKE_VULKANINFO"\n')

    @property
    def env_d(self) -> Path:
        return self.home / ".config" / "uwsm" / "env.d"

    @property
    def env_file(self) -> Path:
        return self.env_d / ENV_NAME

    @property
    def marker(self) -> Path:
        return self.home / ".local" / "state" / "hyprconf" / "vulkan-gpu-ignored"

    def gum_calls(self) -> list[list[str]]:
        if not self.calls_file.exists():
            return []
        return [ln.split("\t") for ln in self.calls_file.read_text().splitlines()]

    def env(self, **extra: str) -> dict[str, str]:
        # The two variables the tool looks for and omarchy-update's marker:
        # never inherited from the process running the suite.
        stripped = ("VK_LOADER_DEVICE_ID_FILTER", "PROTON_ENABLE_WAYLAND", "OMARCHY_UPDATE_LOGGED")
        base = {k: v for k, v in os.environ.items() if k not in stripped}
        return {
            **base,
            "PATH": f"{self.bins}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "_HYPRCONF_SYS_PCI": str(self.pci),
            "_HYPRCONF_SYS_DRM": str(self.drm),
            # An absolute name: found only while the fake exists, never the real one.
            "_HYPRCONF_VULKANINFO": str(self.bins / "vulkaninfo"),
            "_HYPRCONF_UWSM_ENV_D": str(self.env_d),
            "_HYPRCONF_UWSM_ENV": str(self.home / ".config" / "uwsm" / "env"),
            "_HYPRCONF_ENVIRONMENT_D": str(self.home / ".config" / "environment.d"),
            "_HYPRCONF_STATE": str(self.home / ".local" / "state"),
            "_HYPRCONF_ASSUME_TTY": "",
            "FAKE_CALLS": str(self.calls_file),
            "FAKE_GUM_ANSWER": str(self.answer),
            "FAKE_VULKANINFO": str(self.tmp / "vulkaninfo-summary"),
            **extra,
        }

    def run(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(TOOL), *args],
            capture_output=True,
            text=True,
            env=self.env(**extra),
            stdin=subprocess.DEVNULL,
            timeout=60,
        )

    def files(self) -> set[Path]:
        return {p for p in self.home.rglob("*") if p.is_file()}


@pytest.fixture
def dual(tmp_path: Path) -> Box:
    """Two NVIDIA GPUs, the displays on the second by PCI order: the failing case."""
    return Box(tmp_path, [NV_3070, NV_5090])


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


def test_single_gpu_nothing_to_do(tmp_path: Path) -> None:
    box = Box(tmp_path, [NV_5090])
    r = box.run("status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0000:0a:00.0  10de:2b85  NVIDIA  connected outputs: 2" in r.stdout
    assert "nothing to do — 1 GPU" in r.stdout
    p = box.run("prompt", _HYPRCONF_ASSUME_TTY="1")
    assert p.returncode == 0 and p.stdout == "" and box.files() == set() and box.gum_calls() == []


def test_display_on_second_gpu_is_at_risk(dual: Box) -> None:
    r = dual.run("status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "0000:04:00.0  10de:2484  NVIDIA  connected outputs: 0" in r.stdout
    assert "0000:0a:00.0  10de:2b85  NVIDIA  connected outputs: 2" in r.stdout
    assert "display GPU:      0000:0a:00.0 (10de:2b85)" in r.stdout
    assert "Vulkan device 0:  10de:2484 (assumed PCI order; vulkaninfo not found)" in r.stdout
    assert "configured:       no" in r.stdout
    assert "AT RISK" in r.stdout and "hyprconf-vulkan-gpu fix" in r.stdout
    q = dual.run("status", "--quiet")
    assert q.returncode == 3 and q.stdout == "" and q.stderr == ""


def test_displays_on_first_gpu_nothing_to_do(tmp_path: Path) -> None:
    box = Box(tmp_path, [{**NV_3070, "connected": 1}, {**NV_5090, "connected": 0}])
    r = box.run("status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "display GPU:      0000:04:00.0 (10de:2484)" in r.stdout
    assert "the display GPU is Vulkan device 0" in r.stdout
    assert box.run("status", "--quiet").returncode == 0


@pytest.mark.parametrize(
    ("first_connected", "winner", "rc"),
    [(1, "0000:0a:00.0 (10de:2b85)", 3), (2, "0000:04:00.0 (10de:2484)", 0)],
    ids=["most-wins", "tie-lowest-address"],
)
def test_most_connected_outputs_wins_and_is_said(
    tmp_path: Path, first_connected: int, winner: str, rc: int
) -> None:
    # NV_5090 has two connected outputs: 1 loses to it, 2 ties and the lower
    # PCI address (the first GPU, Vulkan device 0 by PCI order) is picked.
    box = Box(tmp_path, [{**NV_3070, "connected": first_connected}, NV_5090])
    r = box.run("status")
    assert r.returncode == rc, r.stdout + r.stderr
    assert (
        f"display GPU:      {winner} — several GPUs have outputs; "
        "most connected wins, tie -> lowest PCI address" in r.stdout
    )


def test_no_connected_output_nothing_to_pin(tmp_path: Path) -> None:
    box = Box(tmp_path, [NV_3070, {**NV_5090, "connected": 0}])
    r = box.run("status")
    assert r.returncode == 0
    assert "display GPU:      none" in r.stdout and "nothing to pin" in r.stdout
    f = box.run("fix")
    assert f.returncode == 1 and "cannot tell which one to pin" in f.stderr


def test_vulkaninfo_order_beats_pci_order(dual: Box) -> None:
    dual.vulkaninfo(vulkaninfo_summary(NV_5090, NV_3070))
    r = dual.run("status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Vulkan device 0:  10de:2b85 (vulkaninfo GPU0)" in r.stdout
    assert "the display GPU is Vulkan device 0" in r.stdout


def test_vulkaninfo_confirms_the_risk(tmp_path: Path) -> None:
    # PCI order would clear this box (displays on the first GPU); vulkaninfo says otherwise.
    box = Box(tmp_path, [{**NV_3070, "connected": 1}, {**NV_5090, "connected": 0}])
    box.vulkaninfo(vulkaninfo_summary(NV_5090, NV_3070))
    r = box.run("status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Vulkan device 0:  10de:2b85 (vulkaninfo GPU0)" in r.stdout


def test_vulkaninfo_uppercase_ids_are_matched(dual: Box) -> None:
    dual.vulkaninfo(vulkaninfo_summary({**NV_5090, "device": "0x2B85"}, NV_3070))
    assert dual.run("status", "--quiet").returncode == 0


def test_a_failing_vulkaninfo_is_not_reported_as_absent(dual: Box) -> None:
    # vulkan-tools installed but no usable ICD: the fallback says so, rather
    # than sending the user to install what they already have.
    dual.vulkaninfo(None)
    r = dual.run("status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "Vulkan device 0:  10de:2484 (assumed PCI order; vulkaninfo gave no GPU0)" in r.stdout
    assert "not found" not in r.stdout


def test_reads_nothing_outside_the_seams(tmp_path: Path) -> None:
    """Every seam at an empty tree: the tool must find no GPU and no config —
    whatever the real box has."""
    box = Box(tmp_path, [])
    r = box.run("status")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"none under {box.pci}" in r.stdout
    assert "display GPU:      none" in r.stdout
    assert "Vulkan device 0:  unknown" in r.stdout
    assert "configured:       no" in r.stdout
    assert "nothing to do — 0 GPU" in r.stdout


@pytest.mark.parametrize("seam", ["_HYPRCONF_SYS_PCI", "_HYPRCONF_SYS_DRM"])
@pytest.mark.parametrize("sub", ["status", "prompt", "fix"])
def test_unreadable_sysfs_is_an_error(dual: Box, seam: str, sub: str) -> None:
    """A seam at a file, not a tree: exit 1 (install.sh turns it into a
    warning), nothing written, nothing asked."""
    broken = dual.tmp / "not-a-sysfs"
    broken.write_text("")
    r = dual.run(sub, _HYPRCONF_ASSUME_TTY="1", **{seam: str(broken)})
    assert r.returncode == 1, r.stdout + r.stderr
    assert "hyprconf-vulkan-gpu: cannot read sysfs" in r.stderr and str(broken) in r.stderr
    assert r.stdout == "" and dual.files() == set() and dual.gum_calls() == []


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
def test_already_configured_is_reported_and_never_prompted(dual: Box, where: str) -> None:
    mention, extra = _configured(dual, where)
    before = dual.files()
    r = dual.run("status", **extra)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"configured:       {mention}" in r.stdout
    assert "already configured" in r.stdout
    p = dual.run("prompt", _HYPRCONF_ASSUME_TTY="1", **extra)
    assert p.returncode == 0 and p.stdout == ""
    assert dual.files() == before and dual.gum_calls() == []


def test_commented_lines_do_not_count(dual: Box) -> None:
    f = dual.home / ".config" / "environment.d" / "old.conf"
    f.parent.mkdir(parents=True)
    f.write_text("# VK_LOADER_DEVICE_ID_FILTER=0x2b85\n#export PROTON_ENABLE_WAYLAND=1\n")
    r = dual.run("status")
    assert r.returncode == 3 and "configured:       no" in r.stdout


# ---------------------------------------------------------------------------
# fix / alt / ignore / remove
# ---------------------------------------------------------------------------


def test_fix_writes_the_four_lines_for_the_display_gpu(dual: Box) -> None:
    r = dual.run("fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(dual.env_file) == FIX_LINES
    head = dual.env_file.read_text().splitlines()[:2]
    assert all(ln.startswith("#") for ln in head)
    assert (
        "0000:0a:00.0 (NVIDIA 10de:2b85)" in head[0]
        and "0000:04:00.0 (NVIDIA 10de:2484)" in head[1]
    )
    assert f"wrote {dual.env_file}" in r.stdout and "re-login to apply" in r.stdout
    assert sourced(
        dual.env_file,
        "VK_LOADER_DEVICE_ID_FILTER",
        "VK_LOADER_DEVICE_SELECT",
        "__NV_PRIME_RENDER_OFFLOAD",
        "__VK_LAYER_NV_optimus",
    ) == ["0x2b85", "10de:2b85", "1", "NVIDIA_only"]
    assert dual.files() == {dual.env_file}
    s = dual.run("status")
    assert s.returncode == 0 and f"VK_LOADER_DEVICE_ID_FILTER in {dual.env_file}" in s.stdout


def test_amd_display_gpu_gets_loader_lines_only(tmp_path: Path) -> None:
    box = Box(tmp_path, [NV_3070, AMD_7900_DISPLAY])
    r = box.run("fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(box.env_file) == [
        "export VK_LOADER_DEVICE_ID_FILTER=0x744c",
        "export VK_LOADER_DEVICE_SELECT=1002:744c",
    ]
    assert "(AMD 1002:744c)" in box.env_file.read_text()


def test_first_nvidia_gpu_behind_amd_gets_no_nv_pair(tmp_path: Path) -> None:
    box = Box(tmp_path, [AMD_7900, NV_5090])
    r = box.run("fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(box.env_file) == LOADER_LINES


def test_nv_pair_needs_an_nvidia_gpu_ahead_in_pci_order(tmp_path: Path) -> None:
    # NVIDIA display GPU first, another NVIDIA GPU behind it: nothing to fix,
    # but a forced fix must not add the pair (the driver's GPU 0 is the display GPU).
    box = Box(tmp_path, [{**NV_5090, "addr": "0000:01:00.0"}, {**NV_3070, "connected": 0}])
    assert box.run("status", "--quiet").returncode == 0
    r = box.run("fix")
    assert r.returncode == 0 and exports(box.env_file) == LOADER_LINES


def test_three_gpus_names_every_hidden_one(tmp_path: Path) -> None:
    box = Box(tmp_path, [INTEL_IGPU, NV_3070, NV_5090])
    r = box.run("fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(box.env_file) == FIX_LINES
    assert (
        "0000:00:02.0 (Intel 8086:a780), 0000:04:00.0 (NVIDIA 10de:2484)"
        in box.env_file.read_text()
    )


def test_fix_is_idempotent(dual: Box) -> None:
    assert dual.run("fix").returncode == 0
    content = dual.env_file.read_bytes()
    old = 1_600_000_000
    os.utime(dual.env_file, (old, old))
    r = dual.run("fix")
    assert r.returncode == 0 and "already current" in r.stdout and "wrote" not in r.stdout
    assert dual.env_file.read_bytes() == content
    assert dual.env_file.stat().st_mtime == old


def test_fix_refuses_on_a_single_gpu_box(tmp_path: Path) -> None:
    box = Box(tmp_path, [NV_5090])
    r = box.run("fix")
    assert r.returncode == 1 and "single-GPU" in r.stderr and box.files() == set()


def test_fix_drops_the_ignore_marker(dual: Box) -> None:
    assert dual.run("ignore").returncode == 0 and dual.marker.exists()
    assert dual.run("fix").returncode == 0
    assert not dual.marker.exists()


def test_alt_writes_proton_wayland_only(dual: Box) -> None:
    r = dual.run("alt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(dual.env_file) == ALT_LINES
    assert dual.env_file.read_text().startswith("# hyprconf-vulkan-gpu:")
    assert sourced(dual.env_file, "PROTON_ENABLE_WAYLAND", "VK_LOADER_DEVICE_ID_FILTER") == [
        "1",
        "",
    ]
    assert "re-login to apply" in r.stdout
    again = dual.run("alt")
    assert again.returncode == 0 and "already current" in again.stdout
    s = dual.run("status")
    assert s.returncode == 0 and f"PROTON_ENABLE_WAYLAND in {dual.env_file}" in s.stdout


def test_ignore_writes_the_marker_and_silences_prompt(dual: Box) -> None:
    r = dual.run("ignore")
    assert r.returncode == 0 and dual.marker.exists() and f"wrote {dual.marker}" in r.stdout
    assert dual.run("status", "--quiet").returncode == 3  # still at risk, only the question is gone
    p = dual.run("prompt", _HYPRCONF_ASSUME_TTY="1")
    assert p.returncode == 0 and p.stdout == ""
    assert dual.files() == {dual.marker} and dual.gum_calls() == []


def test_remove_deletes_file_and_marker(dual: Box) -> None:
    assert dual.run("fix").returncode == 0 and dual.run("ignore").returncode == 0
    r = dual.run("remove")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"removed {dual.env_file}" in r.stdout and f"removed {dual.marker}" in r.stdout
    assert dual.files() == set()
    again = dual.run("remove")
    assert again.returncode == 0 and "nothing to remove" in again.stdout


# ---------------------------------------------------------------------------
# prompt (install.sh's stage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [{}, {"_HYPRCONF_ASSUME_TTY": "1", "OMARCHY_UPDATE_LOGGED": "1"}],
    ids=["no-terminal", "omarchy-update"],
)
def test_prompt_without_a_terminal_is_one_line_and_no_gum(dual: Box, extra: dict[str, str]) -> None:
    """No terminal — or the post-update hook's run inside omarchy-update,
    which has a pty (it re-execs under script(1), so the tty test passes) but
    nobody to answer: its OMARCHY_UPDATE_LOGGED marker wins over the tty."""
    r = dual.run("prompt", **extra)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("\n") == 1 and r.stdout.startswith("hyprconf-vulkan-gpu: ")
    assert "0000:0a:00.0" in r.stdout
    assert dual.files() == set() and dual.gum_calls() == []


def test_prompt_explains_and_offers_three_options(dual: Box) -> None:
    dual.answer.write_text("Fix — write the Vulkan filter to 50-hyprconf-vulkan-gpu\n")
    r = dual.run("prompt", _HYPRCONF_ASSUME_TTY="1")
    assert r.returncode == 0, r.stdout + r.stderr
    text = r.stdout
    assert "0000:0a:00.0 (NVIDIA 10de:2b85)" in text and "10de:2484 (assumed PCI order" in text
    assert "RandR" in text and "CreateSwapChainForHwnd" in text
    assert str(dual.env_file) in text and str(dual.marker) in text
    for ln in FIX_LINES:
        assert ln in text
    assert "PROTON_ENABLE_WAYLAND=1" in text and "Wayland-capable Proton" in text
    assert "never asked again" in text and "'hyprconf-vulkan-gpu fix' stays available" in text
    calls = dual.gum_calls()
    assert len(calls) == 1
    gum = calls[0]
    assert gum[:3] == ["gum", "choose", "--header"]
    assert [o.split()[0] for o in gum[4:]] == ["Fix", "Alt", "Ignore"]


@pytest.mark.parametrize(
    ("answer", "expect"),
    [
        ("Fix", FIX_LINES),
        ("Alt", ALT_LINES),
        ("Ignore", None),
    ],
)
def test_prompt_applies_the_choice(dual: Box, answer: str, expect: list[str] | None) -> None:
    dual.answer.write_text(f"{answer} — whatever gum echoes back\n")
    r = dual.run("prompt", _HYPRCONF_ASSUME_TTY="1")
    assert r.returncode == 0, r.stdout + r.stderr
    if expect is None:
        assert dual.files() == {dual.marker}
    else:
        assert dual.files() == {dual.env_file} and exports(dual.env_file) == expect
        assert "re-login to apply" in r.stdout


def test_prompt_cancelled_changes_nothing(dual: Box) -> None:
    # gum exits non-zero with no output on Esc: the fake does so without an answer file.
    r = dual.run("prompt", _HYPRCONF_ASSUME_TTY="1")
    assert r.returncode == 0 and "nothing changed" in r.stdout
    assert dual.files() == set() and len(dual.gum_calls()) == 1


def test_prompt_without_gum_prints_the_manual_commands(dual: Box) -> None:
    # A PATH of just the tools the script needs, so gum is really absent.
    tools = dual.tmp / "tools"
    tools.mkdir()
    for name in ("bash", "awk", "grep", "sed", "readlink", "cat", "mkdir", "rm"):
        real = shutil.which(name)
        if real is None:
            pytest.skip(f"{name} not installed")
        (tools / name).symlink_to(real)
    r = dual.run("prompt", _HYPRCONF_ASSUME_TTY="1", PATH=str(tools))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gum not found" in r.stdout and "hyprconf-vulkan-gpu fix | alt | ignore" in r.stdout
    assert dual.files() == set()


# ---------------------------------------------------------------------------
# help and hygiene
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["help", "-h", "--help"])
def test_help(dual: Box, arg: str) -> None:
    r = dual.run(arg)
    assert r.returncode == 0
    for sub in (
        "status [--quiet]",
        "prompt",
        "fix",
        "use <gpu>",
        "toggle",
        "run <gpu>",
        "alt",
        "ignore",
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
        "_HYPRCONF_STATE",
        "_HYPRCONF_ASSUME_TTY",
    ):
        assert seam in r.stdout
    assert "RandR" in r.stdout and "VK_LOADER_DEVICE_ID_FILTER" in r.stdout
    assert "OMARCHY_UPDATE_LOGGED" in r.stdout


def test_unknown_subcommand(dual: Box) -> None:
    r = dual.run("bogus")
    assert r.returncode == 1 and "unknown subcommand: bogus" in r.stderr


def test_script_hygiene() -> None:
    text = TOOL.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "readonly" not in text
    assert "MESA_VK_DEVICE_SELECT=" not in text  # Mesa 25 dropped the layer; never set it
    assert TOOL.stat().st_mode & stat.S_IXUSR


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
    assert dual.run("use", "display").returncode == 0
    assert exports(dual.env_file) == FIX_LINES


def test_use_other_pins_the_non_display_gpu_without_the_nv_pair(dual: Box) -> None:
    r = dual.run("use", "other")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(dual.env_file) == LOADER_LINES_3070
    head = dual.env_file.read_text().splitlines()[:2]
    assert "0000:04:00.0 (NVIDIA 10de:2484)" in head[0]
    assert "0000:0a:00.0 (NVIDIA 10de:2b85)" in head[1]
    assert sourced(dual.env_file, "VK_LOADER_DEVICE_SELECT", "__NV_PRIME_RENDER_OFFLOAD") == [
        "10de:2484",
        "",
    ]


@pytest.mark.parametrize("selector", ["0", "0000:04:00.0", "04:00.0", "10de:2484"])
def test_use_accepts_index_address_long_or_short_and_id(dual: Box, selector: str) -> None:
    assert dual.run("use", selector).returncode == 0
    assert exports(dual.env_file) == LOADER_LINES_3070


def test_use_rejects_an_unknown_selector_and_writes_nothing(dual: Box) -> None:
    r = dual.run("use", "nope")
    assert r.returncode == 1 and "no GPU matches 'nope'" in r.stderr
    assert dual.files() == set()


def test_use_without_a_selector_is_a_usage_error(dual: Box) -> None:
    r = dual.run("use")
    assert r.returncode == 1 and "usage: hyprconf-vulkan-gpu use" in r.stderr


def test_use_refuses_on_a_single_gpu_box(tmp_path: Path) -> None:
    box = Box(tmp_path, [NV_5090])
    r = box.run("use", "display")
    assert r.returncode == 1 and "nothing to pin on a single-GPU box" in r.stderr


def test_toggle_starts_from_the_display_gpu_then_swaps_back(dual: Box) -> None:
    first = dual.run("toggle")
    assert first.returncode == 0, first.stdout + first.stderr
    assert exports(dual.env_file) == LOADER_LINES_3070
    assert "0000:0a:00.0 (10de:2b85) -> 0000:04:00.0 (10de:2484)" in first.stdout
    second = dual.run("toggle")
    assert second.returncode == 0, second.stdout + second.stderr
    assert exports(dual.env_file) == FIX_LINES
    assert "0000:04:00.0 (10de:2484) -> 0000:0a:00.0 (10de:2b85)" in second.stdout


def test_toggle_refuses_on_a_single_gpu_box(tmp_path: Path) -> None:
    box = Box(tmp_path, [NV_5090])
    r = box.run("toggle")
    assert r.returncode == 1 and "nothing to toggle on a single-GPU box" in r.stderr


@pytest.mark.parametrize("args", [("use", "other"), ("toggle",)])
def test_use_and_toggle_name_a_setting_outside_their_own_file(dual: Box, args: tuple) -> None:
    stray = dual.home / ".config" / "environment.d" / "50-mine.conf"
    stray.parent.mkdir(parents=True)
    stray.write_text("VK_LOADER_DEVICE_ID_FILTER=0x2b85\n")
    r = dual.run(*args)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "also set outside" in r.stdout and str(stray) in r.stdout
    assert exports(dual.env_file) == LOADER_LINES_3070


def test_run_sets_the_variables_for_one_command_and_writes_nothing(dual: Box) -> None:
    r = dual.run("run", "display", "--", "env")
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
    r = dual.run(
        "run",
        "other",
        "--",
        "env",
        __NV_PRIME_RENDER_OFFLOAD="1",
        __VK_LAYER_NV_optimus="NVIDIA_only",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VK_LOADER_DEVICE_SELECT=10de:2484" in r.stdout
    assert "__NV_PRIME_RENDER_OFFLOAD" not in r.stdout
    assert "__VK_LAYER_NV_optimus" not in r.stdout


def test_run_takes_the_command_without_a_double_dash(dual: Box) -> None:
    r = dual.run("run", "display", "env")
    assert r.returncode == 0 and "VK_LOADER_DEVICE_SELECT=10de:2b85" in r.stdout


def test_run_without_a_command_is_a_usage_error(dual: Box) -> None:
    r = dual.run("run", "display")
    assert r.returncode == 1 and "no command given" in r.stderr


# Two cards with the same vendor:device: the loader's id filter cannot tell
# them apart, so every id-keyed promise must refuse instead of lying.
NV_3070_TWIN = {**NV_3070, "addr": "0000:0b:00.0", "connected": 2}


@pytest.fixture
def twins(tmp_path: Path) -> Box:
    """Two identical NVIDIA cards, the displays on the second."""
    return Box(tmp_path, [NV_3070, NV_3070_TWIN])


@pytest.mark.parametrize("args", [("fix",), ("use", "display"), ("use", "1"), ("toggle",)])
def test_identical_gpu_ids_refuse_to_write_a_pin(twins: Box, args: tuple) -> None:
    r = twins.run(*args)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "sharing id 10de:2484" in r.stderr and "cannot separate identical cards" in r.stderr
    assert not twins.env_file.exists()


def test_identical_gpu_ids_refuse_to_run(twins: Box) -> None:
    r = twins.run("run", "display", "--", "env")
    assert r.returncode == 1 and "sharing id 10de:2484" in r.stderr


def test_identical_gpu_ids_status_says_cannot_tell(twins: Box) -> None:
    r = twins.run("status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "cannot tell — two GPUs share id 10de:2484" in r.stdout


def test_no_arg_subcommands_reject_leftover_arguments(dual: Box) -> None:
    """`toggle other` must die pointing at `use`, never silently plain-toggle."""
    r = dual.run("toggle", "other")
    assert r.returncode == 1
    assert "toggle takes no arguments (did you mean: use other?)" in r.stderr
    assert not dual.env_file.exists()
    for cmd in ("fix", "alt", "ignore", "remove", "prompt"):
        r = dual.run(cmd, "stray")
        assert r.returncode == 1 and f"{cmd} takes no arguments" in r.stderr, cmd


def test_use_toggle_run_never_probe_vulkan(dual: Box) -> None:
    """`run` sits on every game launch: probing every ICD there would wake a
    runtime-suspended GPU. Only status/prompt/fix may pay for vulkaninfo."""
    dual._fake(
        "vulkaninfo",
        'printf \'vulkaninfo\\n\' >> "$FAKE_CALLS"\n[[ $1 == --summary ]] && cat "$FAKE_VULKANINFO"\n',
    )
    (dual.tmp / "vulkaninfo-summary").write_text(vulkaninfo_summary(NV_3070, NV_5090))
    for args in (("use", "other"), ("toggle",), ("run", "other", "--", "true")):
        dual.calls_file.write_text("")
        r = dual.run(*args)
        assert r.returncode == 0, (args, r.stdout + r.stderr)
        assert "vulkaninfo" not in dual.calls_file.read_text(), args
    dual.calls_file.write_text("")
    assert dual.run("status").returncode in (0, 3)
    assert "vulkaninfo" in dual.calls_file.read_text()
