"""modules/vulkan-gpu — the dual-GPU Vulkan pin tool and the one link onto PATH.
Hermetic on conftest's box plus `gpus()`: sysfs is a tmp tree behind
_HYPRCONF_SYS_PCI / _HYPRCONF_SYS_DRM, vulkaninfo a fake behind its own seam."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
TOOL = MODULE / "bin" / "hyprconf-vulkan-gpu"

# GPUs as sysfs prints them: vendor/device lowercase 0x-hex, class 0x03xxxx.
NV_3070 = {"addr": "0000:04:00.0", "vendor": "0x10de", "device": "0x2484", "connected": 0}
NV_5090 = {"addr": "0000:0a:00.0", "vendor": "0x10de", "device": "0x2b85", "connected": 2}
NV_3070_LIT = {**NV_3070, "connected": 1}
NV_3070_2LIT = {**NV_3070, "connected": 2}
NV_5090_DARK = {**NV_5090, "connected": 0}
AMD_7900 = {"addr": "0000:03:00.0", "vendor": "0x1002", "device": "0x744c", "connected": 0}
AMD_DISPLAY = {**AMD_7900, "addr": "0000:0c:00.0", "connected": 1}
INTEL_IGPU = {"addr": "0000:00:02.0", "vendor": "0x8086", "device": "0xa780", "connected": 0}
# Two cards with one vendor:device: the loader filters by id, so it cannot
# separate them and every id-keyed promise must refuse instead of lying.
TWINS = (NV_3070, {**NV_3070, "addr": "0000:0b:00.0", "connected": 2})
# The failing case: the displays on the second GPU in PCI order.
DUAL = (NV_3070, NV_5090)

FILTER = "VK_LOADER_DEVICE_ID_FILTER"
SELECT = "VK_LOADER_DEVICE_SELECT"
WAYLAND = "PROTON_ENABLE_WAYLAND"
LOADER_5090 = [f"export {FILTER}=0x2b85", f"export {SELECT}=10de:2b85"]
LOADER_3070 = [f"export {FILTER}=0x2484", f"export {SELECT}=10de:2484"]
LOADER_AMD = [f"export {FILTER}=0x744c", f"export {SELECT}=1002:744c"]
NV_PAIR = ["export __NV_PRIME_RENDER_OFFLOAD=1", "export __VK_LAYER_NV_optimus=NVIDIA_only"]
FIX_LINES = LOADER_5090 + NV_PAIR
# The display-GPU pick, said in full whenever more than one GPU has an output.
MULTI = " — several GPUs have outputs; most connected wins, tie -> lowest PCI address"


def w(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def vulkaninfo_summary(*cards: dict) -> str:
    """`vulkaninfo --summary`'s Devices section, GPU0 first (vulkan-tools 1.4)."""
    return "Devices:\n========\n" + "".join(
        f"GPU{i}:\n\tvendorID           = {g['vendor']}\n\tdeviceID           = {g['device']}\n"
        for i, g in enumerate(cards)
    )


# GPU0 is the 5090, with an uppercase device id the awk must fold.
VK_5090_FIRST = vulkaninfo_summary({**NV_5090, "device": "0x2B85"}, NV_3070)


def gpus(box: Box, *cards: dict) -> Box:
    """A fake sysfs behind the tool's two seams: a PCI dir per GPU (plus one
    non-GPU device, to be ignored), a DRM card linking to it, and one connected
    connector per requested output plus one disconnected."""
    pci, drm = box.tmp / "sys-pci", box.tmp / "sys-drm"
    for d in (pci, drm):
        d.mkdir()
    for n, g in enumerate(cards, start=1):
        for key, val in (("class", "0x030000"), ("vendor", g["vendor"]), ("device", g["device"])):
            w(pci / g["addr"] / key, val + "\n")
        (drm / f"card{n}").mkdir()
        (drm / f"card{n}" / "device").symlink_to(pci / g["addr"])
        for k in range(g["connected"] + 1):
            lit = "connected\n" if k < g["connected"] else "disconnected\n"
            w(drm / f"card{n}-DP-{k + 1}" / "status", lit)
    for key, val in (("class", "0x020000"), ("vendor", "0x8086"), ("device", "0x15f3")):
        w(pci / "0000:06:00.0" / key, val + "\n")
    box.env.update(
        _HYPRCONF_SYS_PCI=str(pci),
        _HYPRCONF_SYS_DRM=str(drm),
        # An absolute name: found only while this box's fake exists, never the
        # real vulkaninfo (nor the shared fake behind it on PATH).
        _HYPRCONF_VULKANINFO=str(box.bins / "vulkaninfo"),
    )
    return box


def run(box: Box, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return box.run(TOOL, *args, **kwargs)


def vulkaninfo(box: Box, summary: str | None) -> None:
    """A recording vulkaninfo printing `summary`; None: one that fails (no ICD)."""
    body = "echo 'ERROR: [Loader Message] no ICD' >&2\nexit 1\n"
    if summary is not None:
        body = f"[[ $1 == --summary ]] && cat <<'SUMMARY'\n{summary}SUMMARY\n"
    box.stub("vulkaninfo", body)


def env_file(box: Box) -> Path:
    return box.home / ".config" / "uwsm" / "env.d" / "50-hyprconf-vulkan-gpu"


def linked_tool(box: Box) -> Path:
    return box.home / ".local" / "bin" / "hyprconf-vulkan-gpu"


def exports(path: Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines() if ln.startswith("export ")]


@pytest.fixture
def dual(box: Box) -> Box:
    """Two NVIDIA GPUs, the displays on the second by PCI order: the failing case."""
    return gpus(box, *DUAL)


def test_install_links_the_tool_onto_path(box: Box) -> None:
    """~/.local/bin is on the session PATH (default/bash/env-bootstrap:37-40, Omarchy 4.0.3-1)."""
    r = box.run(INSTALL)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.readlink(linked_tool(box)) == str(TOOL) and os.access(linked_tool(box), os.X_OK)
    assert box.files() == {linked_tool(box)}
    assert box.commands == []  # no package, no omarchy command, no sudo, no TTY


def test_a_second_run_writes_nothing(box: Box) -> None:
    assert box.run(INSTALL).returncode == 0
    before = box.snapshot()
    box.reset()
    again = box.run(INSTALL)
    assert again.returncode == 0, again.stdout + again.stderr
    assert box.snapshot() == before  # the inode too: no `ln -sfn` over a good link
    assert again.stdout == "" and box.commands == []


def test_install_replaces_the_pre_module_copy(box: Box) -> None:
    """A hyprconf 7.x install.sh left a rendered regular file at that name."""
    w(linked_tool(box), "#!/usr/bin/env bash\n# an older, copied hyprconf-vulkan-gpu\n")
    assert box.run(INSTALL).returncode == 0
    assert os.readlink(linked_tool(box)) == str(TOOL)


def test_undo_removes_the_link_and_leaves_the_pin(dual: Box) -> None:
    """A pin is a choice of the user's: `hyprconf-vulkan-gpu remove` stays theirs."""
    assert dual.run(INSTALL).returncode == 0 and run(dual, "fix").returncode == 0
    r = dual.undo("vulkan-gpu")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not linked_tool(dual).exists() and not linked_tool(dual).is_symlink()
    assert dual.files() == {env_file(dual)}
    assert "remove" in r.stdout  # says how to drop the pin too


def test_undo_touches_nothing_it_did_not_link(box: Box) -> None:
    assert box.undo("vulkan-gpu").returncode == 0  # never installed
    assert box.files() == set() and box.commands == []
    w(linked_tool(box), "#!/usr/bin/env bash\n# mine\n")
    before = box.snapshot()
    assert box.undo("vulkan-gpu").returncode == 0 and box.snapshot() == before


def test_status_prints_the_picture(dual: Box) -> None:
    r = run(dual, "status")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "0000:04:00.0  10de:2484  NVIDIA  connected outputs: 0" in r.stdout
    assert "0000:0a:00.0  10de:2b85  NVIDIA  connected outputs: 2" in r.stdout
    assert "display GPU:      0000:0a:00.0 (10de:2b85)" in r.stdout
    assert "Vulkan device 0:  10de:2484 (assumed PCI order; vulkaninfo not found)" in r.stdout
    assert "configured:       no" in r.stdout
    assert "AT RISK" in r.stdout and "hyprconf-vulkan-gpu fix" in r.stdout
    assert dual.files() == set()


@pytest.mark.parametrize(
    ("cards", "rc", "verdict"),
    [
        ((), 0, "nothing to do — 0 GPU"),
        ((NV_5090,), 0, "nothing to do — 1 GPU"),
        ((NV_3070, NV_5090_DARK), 0, "no GPU has a connected output"),
        ((NV_3070_LIT, NV_5090_DARK), 0, "the display GPU is Vulkan device 0"),
        (TWINS, 3, "cannot tell — two GPUs share id 10de:2484"),
        ((NV_3070_LIT, NV_5090), 3, f"display GPU:      0000:0a:00.0 (10de:2b85){MULTI}"),
        ((NV_3070_2LIT, NV_5090), 0, f"display GPU:      0000:04:00.0 (10de:2484){MULTI}"),
    ],
    ids=["none", "1gpu", "no-output", "device-0", "twins", "most-wins", "tie-lowest-addr"],
)
def test_status_verdict_and_exit_code(box: Box, cards: tuple, rc: int, verdict: str) -> None:
    """The last two: NV_5090 has two connected outputs, so one loses to it and
    two ties, where the lower PCI address (Vulkan device 0 here) wins."""
    gpus(box, *cards)
    r = run(box, "status")
    assert r.returncode == rc, r.stdout + r.stderr
    assert verdict in r.stdout and box.files() == set()


@pytest.mark.parametrize(
    ("summary", "rc", "device0"),
    [
        (VK_5090_FIRST, 0, "10de:2b85 (vulkaninfo GPU0)"),
        (None, 3, "10de:2484 (assumed PCI order; vulkaninfo gave no GPU0)"),
    ],
    ids=["enumeration-beats-pci-order", "a-failing-probe-is-not-an-absent-one"],
)
def test_vulkan_device_0_comes_from_vulkaninfo(dual: Box, summary, rc, device0) -> None:
    """Case-insensitively, and installed-but-no-ICD never reads as not installed."""
    vulkaninfo(dual, summary)
    r = run(dual, "status")
    assert r.returncode == rc, r.stdout + r.stderr
    assert f"Vulkan device 0:  {device0}" in r.stdout


def test_unreadable_sysfs_is_an_error(dual: Box) -> None:
    """A seam at a file, not a tree: one `[[ -d && -d ]]` covers both seams."""
    broken = w(dual.tmp / "not-a-sysfs", "")
    r = run(dual, "status", env={"_HYPRCONF_SYS_PCI": str(broken)})
    assert r.returncode == 1, r.stdout + r.stderr
    assert "hyprconf-vulkan-gpu: cannot read sysfs" in r.stderr and str(broken) in r.stderr
    assert r.stdout == "" and dual.files() == set()


@pytest.mark.parametrize(
    ("rel", "text", "var"),
    [
        (".config/environment.d/50-mine.conf", f"# hand-written\n{FILTER}=0x2b85\n", FILTER),
        (".config/uwsm/env.d/10-mine", f"export FOO=1\n  export {WAYLAND}=1\n", WAYLAND),
        (".config/uwsm/env", f"export {FILTER}=0x2b85\n", FILTER),
        (".config/uwsm/env-hyprland", f"export {FILTER}=0x2b85\n", FILTER),
        (".config/uwsm/env-hyprland.d/10-mine", f"export {WAYLAND}=1\n", WAYLAND),
        (".config/uwsm/default", f"export {FILTER}=0x2b85\n", FILTER),
        (None, "", FILTER),
    ],
    ids=["environment.d", "env.d", "env", "env-hyprland", "env-hyprland.d", "default", "live"],
)
def test_already_configured_is_reported(dual: Box, rel: str | None, text: str, var: str) -> None:
    """Every place a session takes these from (uwsm's `-D Hyprland` names the
    env-hyprland pair, and both of those load after this module's file)."""
    extra: dict[str, str] = {}
    if rel is None:
        where, extra = "the live environment", {var: "0x2b85"}
    else:
        where = str(w(dual.home / rel, text))
    r = run(dual, "status", env=extra)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"configured:       {var} in {where}" in r.stdout and "already configured" in r.stdout


def test_commented_lines_do_not_count(dual: Box) -> None:
    w(dual.home / ".config/environment.d/old.conf", f"# {FILTER}=0x2b85\n#export {WAYLAND}=1\n")
    r = run(dual, "status")
    assert r.returncode == 3 and "configured:       no" in r.stdout


def test_device_select_alone_is_not_configured_but_is_a_conflict(dual: Box) -> None:
    """Reordering leaves the other GPU enumerated (still at risk), and can still
    beat the pin (so `fix` names it)."""
    stray = w(dual.home / ".config/environment.d/50-mine.conf", f"{SELECT}=10de:2484\n")
    s = run(dual, "status")
    assert s.returncode == 3, s.stdout + s.stderr
    assert "configured:       no" in s.stdout and "AT RISK" in s.stdout
    f = run(dual, "fix")
    assert f.returncode == 0, f.stdout + f.stderr
    assert exports(env_file(dual)) == FIX_LINES
    assert "also set outside" in f.stdout and f"{SELECT} in {stray}" in f.stdout
    assert "may win over this pin" in f.stdout


def test_fix_writes_the_four_lines_for_the_display_gpu(dual: Box) -> None:
    r = run(dual, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(dual)) == FIX_LINES
    head = env_file(dual).read_text().splitlines()[:2]
    assert all(ln.startswith("#") for ln in head)
    assert "0000:0a:00.0 (NVIDIA 10de:2b85)" in head[0]  # pinned
    assert "0000:04:00.0 (NVIDIA 10de:2484)" in head[1]  # hidden
    assert f"wrote {env_file(dual)}" in r.stdout and "re-login to apply" in r.stdout
    # What uwsm's `sh` takes out of it, in an environment with no live
    # VK_LOADER_* of the developer's.
    sh = subprocess.run(
        ["sh", "-c", f'. "$1"; printf "%s\\n" "${FILTER}" "${SELECT}"', "sh", str(env_file(dual))],
        capture_output=True,
        text=True,
        check=True,
        env={"PATH": os.environ["PATH"]},
    )
    assert sh.stdout.splitlines() == ["0x2b85", "10de:2b85"]
    assert dual.files() == {env_file(dual)}


@pytest.mark.parametrize(
    ("cards", "lines"),
    [((NV_3070, AMD_DISPLAY), LOADER_AMD), ((AMD_7900, NV_5090), LOADER_5090)],
    ids=["target-not-nvidia", "no-nvidia-ahead"],
)
def test_the_nv_pair_needs_an_nvidia_gpu_ahead_of_an_nvidia_target(box: Box, cards, lines) -> None:
    """Otherwise offload has nothing to offload from."""
    gpus(box, *cards)
    r = run(box, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(box)) == lines


def test_three_gpus_names_every_hidden_one(box: Box) -> None:
    gpus(box, INTEL_IGPU, NV_3070, NV_5090)
    r = run(box, "fix")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(box)) == FIX_LINES
    hidden = "0000:00:02.0 (Intel 8086:a780), 0000:04:00.0 (NVIDIA 10de:2484)"
    assert hidden in env_file(box).read_text()


def test_fix_is_idempotent(dual: Box) -> None:
    assert run(dual, "fix").returncode == 0
    content, old = env_file(dual).read_bytes(), 1_600_000_000
    os.utime(env_file(dual), (old, old))
    r = run(dual, "fix")
    assert r.returncode == 0 and "already current" in r.stdout and "wrote" not in r.stdout
    assert env_file(dual).read_bytes() == content
    assert env_file(dual).stat().st_mtime == old


# Every refusal: a selector that cannot be honoured, and a usage error.
REFUSED = {
    "fix1": ((NV_5090,), ("fix",), "nothing to pin on a single-GPU box"),
    "use1": ((NV_5090,), ("use", "display"), "nothing to pin on a single-GPU box"),
    "dark": ((NV_3070, NV_5090_DARK), ("fix",), "cannot tell which one to pin"),
    "tw-fix": (TWINS, ("fix",), "cannot separate identical cards"),
    "tw-use": (TWINS, ("use", "display"), "cannot separate identical cards"),
    "tw-run": (TWINS, ("run", "display", "--", "true"), "cannot separate identical cards"),
    "id-sel": (DUAL, ("use", "10de:2484"), "no GPU matches '10de:2484'"),
    "bad-sel": (DUAL, ("run", "x", "--", "touch", "{home}/ran"), "no GPU matches 'x'"),
    "use": (DUAL, ("use",), "usage: hyprconf-vulkan-gpu use"),
    "run": (DUAL, ("run",), "usage: hyprconf-vulkan-gpu run"),
    "run-command": (DUAL, ("run", "display"), "no command given"),
    "no-arg-sub": (DUAL, ("fix", "stray"), "fix takes no arguments (did you mean: use stray?)"),
    "unknown": (DUAL, ("bogus",), "unknown subcommand: bogus"),
}


@pytest.mark.parametrize(("cards", "args", "message"), REFUSED.values(), ids=REFUSED)
def test_it_refuses_rather_than_pin_the_wrong_thing(box: Box, cards, args, message) -> None:
    """An id is no selector (two cards can share one, and then the loader's filter
    cannot separate them at all), and a usage error refuses the same way: exit 1,
    the reason on stderr, nothing written and no `run` command started."""
    gpus(box, *cards)
    r = run(box, *(a.format(home=box.home) for a in args))
    assert r.returncode == 1, r.stdout + r.stderr
    assert message in r.stderr and box.files() == set()


@pytest.mark.parametrize(
    ("selector", "lines"),
    [("display", FIX_LINES), ("other", LOADER_3070), ("0000:04:00.0", LOADER_3070)],
)
def test_use_pins_the_gpu_named(dual: Box, selector: str, lines: list[str]) -> None:
    r = run(dual, "use", selector)
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(dual)) == lines


@pytest.mark.parametrize("args", [("fix",), ("use", "other"), ("run", "other", "--", "true")])
def test_fix_use_and_run_never_probe_vulkaninfo(dual: Box, args: tuple) -> None:
    """A probe creates an instance on every ICD, waking a suspended GPU."""
    vulkaninfo(dual, vulkaninfo_summary(NV_3070, NV_5090))
    assert run(dual, *args).returncode == 0
    assert dual.calls_of("vulkaninfo") == []
    dual.reset()
    # 0 after `fix`/`use` wrote the pin, 3 after `run` left the box as it found it.
    assert run(dual, "status").returncode in (0, 3)
    assert len(dual.calls_of("vulkaninfo")) == 1


def test_run_sets_the_variables_for_one_command_and_writes_nothing(dual: Box) -> None:
    r = run(dual, "run", "display", "--", "env")
    assert r.returncode == 0, r.stdout + r.stderr
    seen = dict(ln.split("=", 1) for ln in r.stdout.splitlines() if "=" in ln)
    assert seen[FILTER] == "0x2b85" and seen[SELECT] == "10de:2b85"
    assert seen["__NV_PRIME_RENDER_OFFLOAD"] == "1"
    assert seen["__VK_LAYER_NV_optimus"] == "NVIDIA_only"
    assert dual.files() == set()


def test_run_clears_an_nv_pair_the_target_must_not_have(dual: Box) -> None:
    """Inheriting the session's pair would offload with nowhere to go."""
    pair = {"__NV_PRIME_RENDER_OFFLOAD": "1", "__VK_LAYER_NV_optimus": "NVIDIA_only"}
    r = run(dual, "run", "other", "--", "env", env=pair)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"{SELECT}=10de:2484" in r.stdout
    assert "__NV_PRIME_RENDER_OFFLOAD" not in r.stdout and "__VK_LAYER_NV_optimus" not in r.stdout


def test_run_passes_the_arguments_through_without_a_double_dash(dual: Box) -> None:
    """`run` stops reading at the selector: the command's own options are its own."""
    r = run(dual, "run", "display", "printf", "%s|%s\n", "-n", "two")
    assert r.returncode == 0 and r.stdout == "-n|two\n"


def test_alt_writes_proton_wayland_only(dual: Box) -> None:
    """The answer when two cards share a vendor:device, which the filter cannot separate."""
    r = run(dual, "alt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert exports(env_file(dual)) == [f"export {WAYLAND}=1"]
    assert env_file(dual).read_text().startswith("# hyprconf-vulkan-gpu:")
    assert FILTER not in env_file(dual).read_text()
    assert "re-login to apply" in r.stdout


def test_remove_deletes_the_env_file(dual: Box) -> None:
    assert run(dual, "fix").returncode == 0
    r = run(dual, "remove")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"removed {env_file(dual)}" in r.stdout and dual.files() == set()
    again = run(dual, "remove")
    assert again.returncode == 0 and "nothing to remove" in again.stdout


def test_help_is_one_text_under_three_names(dual: Box) -> None:
    r = run(dual, "help")
    assert r.returncode == 0 and r.stdout
    assert r.stdout == run(dual, "-h").stdout == run(dual, "--help").stdout
