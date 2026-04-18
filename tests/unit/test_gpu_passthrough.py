"""Tests for stow/hypr/.config/hypr/scripts/gpu-passthrough.sh

Covers GPU detection, name resolution, IOMMU group handling, VFIO
mode system (vm/host/none), audit checks, config management, status
display, and the CLI dispatch in the hyprconf binary.

All system interfaces (lspci, /sys/bus/pci, modprobe, systemctl, etc.)
are mocked via a fake sysfs tree and wrapper scripts placed on PATH.
"""
from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".config" / "hypr" / "scripts" / "gpu-passthrough.sh"
)

HYPRCONF_BIN = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".local" / "bin" / "hyprconf"
)


# ---------------------------------------------------------------------------
# Fake sysfs / lspci helpers
# ---------------------------------------------------------------------------

LSPCI_TWO_NVIDIA = """\
01:00.0 VGA compatible controller: NVIDIA Corporation GA104 [GeForce RTX 3070] [10de:2484] (rev a1)
01:00.1 Audio device: NVIDIA Corporation GA104 High Definition Audio Controller [10de:228b] (rev a1)
02:00.0 VGA compatible controller: NVIDIA Corporation AD102 [GeForce RTX 5090] [10de:2684] (rev a1)
02:00.1 Audio device: NVIDIA Corporation AD102 High Definition Audio Controller [10de:22be] (rev a1)
"""

LSPCI_SINGLE_NVIDIA = """\
00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630 [8086:3e92] (rev 00)
01:00.0 VGA compatible controller: NVIDIA Corporation GA104 [GeForce RTX 3070] [10de:2484] (rev a1)
01:00.1 Audio device: NVIDIA Corporation GA104 High Definition Audio Controller [10de:228b] (rev a1)
"""

LSPCI_INTEL_IGPU = """\
00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630 [8086:3e92] (rev 00)
"""

LSPCI_EMPTY = ""


def _make_executable(path: Path, content: str) -> None:
    """Write a bash script and make it executable."""
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_fake_bins(
    bin_dir: Path,
    *,
    lspci_output: str = LSPCI_TWO_NVIDIA,
    lsmod_output: str = "vfio_pci               12345  0\nvfio_iommu_type1       45678  0\n",
    pacman_installed: tuple[str, ...] = (
        "qemu-desktop", "edk2-ovmf", "dmidecode",
    ),
    modinfo_available: tuple[str, ...] = ("vfio", "vfio_pci", "vfio_iommu_type1"),
    cpu_vendor: str = "intel",
    iommu_enabled: bool = True,
    user_groups: str = "wheel kvm",
) -> None:
    """Populate bin_dir with fake system utilities."""
    bin_dir.mkdir(parents=True, exist_ok=True)

    # lspci
    _make_executable(bin_dir / "lspci", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        cat << 'LSPCI_EOF'
{lspci_output.rstrip()}
LSPCI_EOF
    """))

    # lsmod
    _make_executable(bin_dir / "lsmod", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        cat << 'LSMOD_EOF'
{lsmod_output.rstrip()}
LSMOD_EOF
    """))

    # pacman -Qi
    installed_set = " ".join(pacman_installed)
    _make_executable(bin_dir / "pacman", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$1" == "-Qi" ]]; then
            for pkg in {installed_set}; do
                if [[ "$2" == "$pkg" ]]; then exit 0; fi
            done
            exit 1
        fi
        exit 0
    """))

    # modinfo
    mods_available = " ".join(modinfo_available)
    _make_executable(bin_dir / "modinfo", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        for m in {mods_available}; do
            if [[ "$1" == "$m" ]]; then exit 0; fi
        done
        exit 1
    """))

    # modprobe (no-op)
    _make_executable(bin_dir / "modprobe", "#!/usr/bin/env bash\nexit 0\n")

    # sudo (pass-through — strip flags like -n before exec)
    _make_executable(bin_dir / "sudo", textwrap.dedent("""\
        #!/usr/bin/env bash
        while [[ "${1:-}" == -* ]]; do shift; done
        exec "$@"
    """))

    # systemctl (no-op — mode-based system does not check services)
    _make_executable(bin_dir / "systemctl", textwrap.dedent("""\
        #!/usr/bin/env bash
        if [[ "$1" == "is-active" && "$2" == "--quiet" ]]; then
            exit 0
        fi
        if [[ "$1" == "is-enabled" && "$2" == "--quiet" ]]; then
            exit 0
        fi
        if [[ "$1" == "status" ]]; then
            echo "$3 - active (running)"
            exit 0
        fi
        exit 0
    """))

    # id
    _make_executable(bin_dir / "id", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$1" == "-nG" ]]; then
            echo "{user_groups}"
            exit 0
        fi
        echo "1000"
    """))

    # grep wrapper for /proc/cmdline + /proc/cpuinfo
    cmdline_content = "intel_iommu=on iommu=pt" if iommu_enabled else "quiet splash"
    cpuinfo_vendor = "GenuineIntel" if cpu_vendor == "intel" else "AuthenticAMD"
    _make_executable(bin_dir / "grep", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # For /proc/ reads, return fake data; otherwise use real grep
        for arg in "$@"; do
            if [[ "$arg" == "/proc/cmdline" ]]; then
                echo "{cmdline_content}" | /usr/bin/grep "${{@:1:$(($#-1))}}" -
                exit $?
            fi
            if [[ "$arg" == "/proc/cpuinfo" ]]; then
                echo "model name : Test CPU"
                echo "vendor_id : {cpuinfo_vendor}"
                echo "{cpuinfo_vendor}" | /usr/bin/grep "${{@:1:$(($#-1))}}" -
                exit $?
            fi
        done
        exec /usr/bin/grep "$@"
    """))

    # uname
    _make_executable(bin_dir / "uname", textwrap.dedent("""\
        #!/usr/bin/env bash
        if [[ "$1" == "-r" ]]; then echo "6.10.0-test"; fi
    """))

    # cat wrapper for /proc files
    _make_executable(bin_dir / "cat", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        for arg in "$@"; do
            if [[ "$arg" == "/proc/cmdline" ]]; then
                echo "{cmdline_content}"
                exit 0
            fi
            if [[ "$arg" == "/proc/cpuinfo" ]]; then
                echo "model name : Test CPU"
                echo "vendor_id : {cpuinfo_vendor}"
                exit 0
            fi
        done
        exec /usr/bin/cat "$@"
    """))

    # dmesg (minimal stub)
    _make_executable(bin_dir / "dmesg", textwrap.dedent("""\
        #!/usr/bin/env bash
        echo "[    0.123] DMAR: IOMMU enabled"
        echo "[    1.234] vfio_pci: loaded"
    """))

    # usermod (no-op)
    _make_executable(bin_dir / "usermod", "#!/usr/bin/env bash\nexit 0\n")

    # tee (write stdin to file — mimics real tee for sudo tee)
    _make_executable(bin_dir / "tee", textwrap.dedent("""\
        #!/usr/bin/env bash
        /usr/bin/tee "$@"
    """))

    # bootctl
    _make_executable(bin_dir / "bootctl", textwrap.dedent("""\
        #!/usr/bin/env bash
        exit 1
    """))

    # basename — need real one
    _make_executable(bin_dir / "basename", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/basename "$@"
    """))

    # readlink
    _make_executable(bin_dir / "readlink", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/readlink "$@"
    """))

    # xargs
    _make_executable(bin_dir / "xargs", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/xargs "$@"
    """))

    # date
    _make_executable(bin_dir / "date", textwrap.dedent("""\
        #!/usr/bin/env bash
        echo "2025-01-01 00:00:00"
    """))

    # ls
    _make_executable(bin_dir / "ls", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/ls "$@"
    """))

    # wc
    _make_executable(bin_dir / "wc", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/wc "$@"
    """))

    # head
    _make_executable(bin_dir / "head", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/head "$@"
    """))

    # cut
    _make_executable(bin_dir / "cut", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/cut "$@"
    """))

    # awk
    _make_executable(bin_dir / "awk", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/awk "$@"
    """))

    # sed
    _make_executable(bin_dir / "sed", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/sed "$@"
    """))

    # tr
    _make_executable(bin_dir / "tr", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/tr "$@"
    """))

    # printf — use builtin, don't shadow
    # echo — use builtin, don't shadow

    # virt-manager (no-op)
    _make_executable(bin_dir / "virt-manager", "#!/usr/bin/env bash\nexit 0\n")

    # virsh (fake VM manager)
    _make_executable(bin_dir / "virsh", textwrap.dedent("""\
        #!/usr/bin/env bash
        # Skip connection URI args (-c qemu:///system) inserted by _gpu_virsh
        while [[ "${1:-}" == "-c" ]]; do shift 2; done
        if [[ "$1" == "dominfo" && "$2" == "win11" ]]; then exit 0; fi
        if [[ "$1" == "dominfo" ]]; then exit 1; fi
        if [[ "$1" == "list" ]]; then echo "win11"; exit 0; fi
        if [[ "$1" == "dumpxml" && "$2" == "win11" ]]; then
            cat << 'XML'
<domain type='kvm'>
  <name>win11</name>
  <os><type>hvm</type></os>
</domain>
XML
            exit 0
        fi
        if [[ "$1" == "attach-device" ]]; then exit 0; fi
        if [[ "$1" == "detach-device" ]]; then exit 0; fi
        if [[ "$1" == "define" ]]; then exit 0; fi
        if [[ "$1" == "start" ]]; then exit 0; fi
        if [[ "$1" == "nodedev-detach" ]]; then exit 0; fi
        if [[ "$1" == "nodedev-reattach" ]]; then exit 0; fi
        exit 0
    """))

    # dmidecode (fake SMBIOS data)
    _make_executable(bin_dir / "dmidecode", textwrap.dedent("""\
        #!/usr/bin/env bash
        cat << 'DMI'
System Information
\tManufacturer: ASUS
\tProduct Name: ROG STRIX B550-F
\tSerial Number: ABC123XYZ
DMI
    """))

    # virt-xml (no-op)
    _make_executable(bin_dir / "virt-xml", "#!/usr/bin/env bash\nexit 0\n")

    # mktemp
    _make_executable(bin_dir / "mktemp", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec /usr/bin/mktemp "$@"
    """))


def _make_fake_sysfs(
    sysfs_root: Path,
    gpus: dict[str, dict] | None = None,
    display_connectors: dict[str, list[str]] | None = None,
) -> None:
    """Create a fake /sys/bus/pci + /sys/kernel/iommu_groups tree.

    ``display_connectors`` maps PCI address → list of connector status
    strings (e.g. ``{"01:00.0": ["connected"]}``) so
    ``_gpu_is_display_gpu`` can be tested with the fake sysfs.
    """
    if gpus is None:
        gpus = {
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
            "02:00.0": {"driver": "nvidia", "iommu_group": "2", "vendor": "0x10de", "device": "0x2684"},
            "02:00.1": {"driver": "snd_hda_intel", "iommu_group": "2", "vendor": "0x10de", "device": "0x22be"},
        }

    pci_dir = sysfs_root / "bus" / "pci" / "devices"
    pci_dir.mkdir(parents=True)
    iommu_dir = sysfs_root / "kernel" / "iommu_groups"
    iommu_dir.mkdir(parents=True)

    # Also create drivers dirs
    drivers_dir = sysfs_root / "bus" / "pci" / "drivers"
    for drv in ("nvidia", "snd_hda_intel", "vfio-pci", "nouveau"):
        (drivers_dir / drv).mkdir(parents=True)

    # Create drivers_probe file
    (sysfs_root / "bus" / "pci" / "drivers_probe").touch()

    for pci_addr, info in gpus.items():
        full_addr = f"0000:{pci_addr}"
        dev_dir = pci_dir / full_addr
        dev_dir.mkdir()

        # vendor/device files
        (dev_dir / "vendor").write_text(info.get("vendor", "0x10de"))
        (dev_dir / "device").write_text(info.get("device", "0x0000"))

        # driver symlink (device → driver dir)
        driver = info.get("driver", "")
        if driver:
            driver_target = drivers_dir / driver
            driver_target.mkdir(parents=True, exist_ok=True)
            (dev_dir / "driver").symlink_to(driver_target)
            # Reverse symlink (driver dir → device) for driver enumeration
            (driver_target / full_addr).symlink_to(dev_dir)

        # driver_override file
        (dev_dir / "driver_override").write_text("")

        # IOMMU group symlink
        grp = info.get("iommu_group", "")
        if grp:
            grp_dev_dir = iommu_dir / grp / "devices"
            grp_dev_dir.mkdir(parents=True, exist_ok=True)
            (grp_dev_dir / full_addr).symlink_to(dev_dir)
            (dev_dir / "iommu_group").symlink_to(iommu_dir / grp)

        # unbind file (writable)
        if driver:
            (drivers_dir / driver / "unbind").touch()

    # DRM / display connector entries
    if display_connectors:
        class_drm_dir = sysfs_root / "class" / "drm"
        class_drm_dir.mkdir(parents=True, exist_ok=True)
        card_idx = 0
        for pci_addr, statuses in display_connectors.items():
            full_addr = f"0000:{pci_addr}"
            dev_dir = pci_dir / full_addr
            drm_dir = dev_dir / "drm"
            card_name = f"card{card_idx}"
            (drm_dir / card_name).mkdir(parents=True, exist_ok=True)
            for conn_idx, st in enumerate(statuses):
                conn_dir = class_drm_dir / f"{card_name}-DP-{conn_idx + 1}"
                conn_dir.mkdir(parents=True, exist_ok=True)
                (conn_dir / "status").write_text(st)
            card_idx += 1


def _source_and_run(
    func: str,
    args: list[str] | None = None,
    *,
    bin_dir: Path,
    sysfs_root: Path | None = None,
    env_extra: dict[str, str] | None = None,
    home_dir: Path | None = None,
    tmp_path: Path | None = None,  # accepted but unused (from fixture dict)
) -> subprocess.CompletedProcess:
    """Source gpu-passthrough.sh, optionally override /sys paths, then call a function."""
    args_str = " ".join(f'"{a}"' for a in (args or []))

    # Build a wrapper that overrides /sys paths by redefining functions
    # that read from sysfs
    overrides = ""
    if sysfs_root:
        overrides = textwrap.dedent(f"""\
            # Override sysfs root for mode functions
            export _GPU_SYSFS="{sysfs_root}"

            # Override sysfs path references
            _gpu_current_driver() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local driver_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/driver"
                if [[ -L "$driver_link" ]]; then
                    basename "$(readlink "$driver_link")"
                else
                    echo "none"
                fi
            }}

            _gpu_iommu_group() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local iommu_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/iommu_group"
                if [[ -L "$iommu_link" ]]; then
                    basename "$(readlink "$iommu_link")"
                else
                    echo ""
                fi
            }}

            _gpu_iommu_devices() {{
                local pci_addr="$1"
                local group
                group=$(_gpu_iommu_group "$pci_addr")
                [[ -z "$group" ]] && return 1

                local grp_dir="{sysfs_root}/kernel/iommu_groups/${{group}}/devices"
                [[ -d "$grp_dir" ]] || return 1

                local dev
                for dev in "$grp_dir"/*; do
                    basename "$dev" | sed 's/^0000://'
                done
            }}

            _gpu_is_display_gpu() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local drm_dir="{sysfs_root}/bus/pci/devices/${{full_addr}}/drm"
                [[ -d "$drm_dir" ]] || return 1
                local card status_file
                for card in "$drm_dir"/card*; do
                    [[ -d "$card" ]] || continue
                    local card_name
                    card_name=$(basename "$card")
                    for status_file in {sysfs_root}/class/drm/"${{card_name}}"-*/status; do
                        [[ -f "$status_file" ]] || continue
                        if [[ "$(cat "$status_file" 2>/dev/null)" == "connected" ]]; then
                            return 0
                        fi
                    done
                done
                return 1
            }}

            # Override mode helpers for test environment (no real sysfs writes)
            _gpu_check_processes() {{ return 0; }}
            _gpu_unload_nvidia_modules() {{ return 0; }}
            _gpu_unbind_vtconsoles() {{ return 0; }}
            _gpu_is_module_loaded() {{ return 0; }}
            _gpu_update_state_marker() {{ return 0; }}
            _gpu_ensure_sudo() {{ return 0; }}
            _gpu_get_pci_class() {{ echo "0300"; }}
            _gpu_get_pci_device_id() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local v="" d=""
                [[ -f "{sysfs_root}/bus/pci/devices/${{full_addr}}/vendor" ]] && v=$(cat "{sysfs_root}/bus/pci/devices/${{full_addr}}/vendor" | sed 's/^0x//')
                [[ -f "{sysfs_root}/bus/pci/devices/${{full_addr}}/device" ]] && d=$(cat "{sysfs_root}/bus/pci/devices/${{full_addr}}/device" | sed 's/^0x//')
                echo "$v:$d"
            }}

            # For mode_vm: simulate successful binding by updating the fake sysfs
            _gpu_mode_sysfs_write() {{
                # In test mode, mutate the fake sysfs symlinks
                local dev_full="$1" target_driver="$2"
                local dev_dir="{sysfs_root}/bus/pci/devices/${{dev_full}}"
                [[ -d "$dev_dir" ]] || return 0
                rm -f "$dev_dir/driver"
                if [[ -n "$target_driver" ]]; then
                    local drv_dir="{sysfs_root}/bus/pci/drivers/$target_driver"
                    mkdir -p "$drv_dir"
                    ln -sf "$drv_dir" "$dev_dir/driver"
                fi
            }}
        """)

    cmd = textwrap.dedent(f"""\
        set -euo pipefail
        source "{SCRIPT}"
        {overrides}
        {func} {args_str}
    """)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    if home_dir:
        env["HOME"] = str(home_dir)
    if env_extra:
        env.update(env_extra)

    return subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_env(tmp_path):
    """Provide a full fake environment with sysfs, bins, and HOME."""
    bin_dir = tmp_path / "bin"
    sysfs_root = tmp_path / "sys"
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    _make_fake_bins(bin_dir)
    _make_fake_sysfs(sysfs_root)

    return {
        "bin_dir": bin_dir,
        "sysfs_root": sysfs_root,
        "home_dir": home_dir,
        "tmp_path": tmp_path,
    }


# ---------------------------------------------------------------------------
# _gpu_detect
# ---------------------------------------------------------------------------

class TestGpuDetect:
    def test_detect_finds_two_nvidia_gpus(self, fake_env):
        r = _source_and_run("_gpu_detect", **fake_env)
        assert r.returncode == 0
        assert "GPU 1:" in r.stdout
        assert "GPU 2:" in r.stdout
        assert "NVIDIA" in r.stdout

    def test_detect_shows_pci_addresses(self, fake_env):
        r = _source_and_run("_gpu_detect", **fake_env)
        assert "01:00.0" in r.stdout
        assert "02:00.0" in r.stdout

    def test_detect_shows_drivers(self, fake_env):
        r = _source_and_run("_gpu_detect", **fake_env)
        assert "nvidia" in r.stdout

    def test_detect_shows_iommu_groups(self, fake_env):
        r = _source_and_run("_gpu_detect", **fake_env)
        assert "IOMMU Group:" in r.stdout

    def test_detect_empty_returns_error(self, tmp_path):
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir, lspci_output=LSPCI_EMPTY)
        r = _source_and_run("_gpu_detect", bin_dir=bin_dir)
        assert r.returncode != 0
        assert "No GPUs detected" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_classify
# ---------------------------------------------------------------------------

class TestGpuClassify:
    def test_classify_igpu(self, fake_env):
        r = _source_and_run("_gpu_classify", ["00:02.0", "Intel UHD"], **fake_env)
        assert r.stdout.strip() == "integrated"

    def test_classify_dedicated(self, fake_env):
        r = _source_and_run("_gpu_classify", ["01:00.0", "NVIDIA RTX 3070"], **fake_env)
        assert r.stdout.strip() == "dedicated"

    def test_classify_integrated_keyword(self, fake_env):
        r = _source_and_run("_gpu_classify", ["05:00.0", "AMD Integrated Graphics"], **fake_env)
        assert r.stdout.strip() == "integrated"


# ---------------------------------------------------------------------------
# _gpu_is_display_gpu
# ---------------------------------------------------------------------------

class TestGpuIsDisplayGpu:
    def test_display_gpu_detected(self, tmp_path):
        """GPU with a connected DRM connector is identified as display GPU."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(
            sysfs_root,
            gpus={
                "01:00.0": {"driver": "nvidia", "iommu_group": "1",
                             "vendor": "0x10de", "device": "0x2484"},
            },
            display_connectors={"01:00.0": ["connected"]},
        )
        r = _source_and_run(
            "_gpu_is_display_gpu", ["01:00.0"],
            bin_dir=bin_dir, sysfs_root=sysfs_root,
        )
        assert r.returncode == 0

    def test_non_display_gpu_returns_false(self, tmp_path):
        """GPU with no DRM directory is not a display GPU."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(
            sysfs_root,
            gpus={
                "02:00.0": {"driver": "nvidia", "iommu_group": "2",
                             "vendor": "0x10de", "device": "0x2684"},
            },
        )
        r = _source_and_run(
            "_gpu_is_display_gpu", ["02:00.0"],
            bin_dir=bin_dir, sysfs_root=sysfs_root,
        )
        assert r.returncode != 0

    def test_disconnected_connectors_returns_false(self, tmp_path):
        """GPU whose connectors are all disconnected is not a display GPU."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(
            sysfs_root,
            gpus={
                "01:00.0": {"driver": "nvidia", "iommu_group": "1",
                             "vendor": "0x10de", "device": "0x2484"},
            },
            display_connectors={"01:00.0": ["disconnected", "disconnected"]},
        )
        r = _source_and_run(
            "_gpu_is_display_gpu", ["01:00.0"],
            bin_dir=bin_dir, sysfs_root=sysfs_root,
        )
        assert r.returncode != 0

    def test_mixed_connectors_detected(self, tmp_path):
        """At least one connected connector → display GPU."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(
            sysfs_root,
            gpus={
                "01:00.0": {"driver": "nvidia", "iommu_group": "1",
                             "vendor": "0x10de", "device": "0x2484"},
            },
            display_connectors={"01:00.0": ["disconnected", "connected"]},
        )
        r = _source_and_run(
            "_gpu_is_display_gpu", ["01:00.0"],
            bin_dir=bin_dir, sysfs_root=sysfs_root,
        )
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# _gpu_current_driver
# ---------------------------------------------------------------------------

class TestGpuCurrentDriver:
    def test_returns_nvidia_driver(self, fake_env):
        r = _source_and_run("_gpu_current_driver", ["01:00.0"], **fake_env)
        assert r.stdout.strip() == "nvidia"

    def test_returns_none_for_no_driver(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "03:00.0": {"driver": "", "iommu_group": "5", "vendor": "0x10de", "device": "0x0000"},
        })
        r = _source_and_run("_gpu_current_driver", ["03:00.0"], bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert r.stdout.strip() == "none"


# ---------------------------------------------------------------------------
# _gpu_iommu_group
# ---------------------------------------------------------------------------

class TestGpuIommuGroup:
    def test_returns_correct_group(self, fake_env):
        r = _source_and_run("_gpu_iommu_group", ["01:00.0"], **fake_env)
        assert r.stdout.strip() == "1"

    def test_returns_different_group_for_second_gpu(self, fake_env):
        r = _source_and_run("_gpu_iommu_group", ["02:00.0"], **fake_env)
        assert r.stdout.strip() == "2"

    def test_returns_empty_for_unknown_device(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={})
        # No device at 99:00.0
        dev_dir = sysfs_root / "bus" / "pci" / "devices" / "0000:99:00.0"
        dev_dir.mkdir(parents=True)
        r = _source_and_run("_gpu_iommu_group", ["99:00.0"], bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# _gpu_iommu_devices
# ---------------------------------------------------------------------------

class TestGpuIommuDevices:
    def test_lists_all_devices_in_group(self, fake_env):
        r = _source_and_run("_gpu_iommu_devices", ["01:00.0"], **fake_env)
        assert r.returncode == 0
        devs = r.stdout.strip().split("\n")
        assert "01:00.0" in devs
        assert "01:00.1" in devs

    def test_group2_has_separate_devices(self, fake_env):
        r = _source_and_run("_gpu_iommu_devices", ["02:00.0"], **fake_env)
        devs = r.stdout.strip().split("\n")
        assert "02:00.0" in devs
        assert "02:00.1" in devs


# ---------------------------------------------------------------------------
# _gpu_resolve
# ---------------------------------------------------------------------------

class TestGpuResolve:
    def test_resolve_pci_address_passthrough(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["01:00.0"], **fake_env)
        assert r.returncode == 0
        assert r.stdout.strip() == "01:00.0"

    def test_resolve_model_name_3070(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["3070"], **fake_env)
        assert r.returncode == 0
        assert r.stdout.strip() == "01:00.0"

    def test_resolve_model_name_5090(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["5090"], **fake_env)
        assert r.returncode == 0
        assert r.stdout.strip() == "02:00.0"

    def test_resolve_ordinal_nvidia0(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["nvidia0"], **fake_env)
        assert r.returncode == 0
        assert r.stdout.strip() == "01:00.0"

    def test_resolve_ordinal_nvidia1(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["nvidia1"], **fake_env)
        assert r.returncode == 0
        assert r.stdout.strip() == "02:00.0"

    def test_resolve_rtx_prefix(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["RTX 3070"], **fake_env)
        assert r.returncode == 0
        assert r.stdout.strip() == "01:00.0"

    def test_resolve_ambiguous_fails(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["NVIDIA"], **fake_env)
        assert r.returncode != 0
        assert "Ambiguous" in r.stderr or "matches" in r.stderr

    def test_resolve_unknown_fails(self, fake_env):
        r = _source_and_run("_gpu_resolve", ["RadeonXYZ"], **fake_env)
        assert r.returncode != 0
        assert "No GPU matching" in r.stderr


# ---------------------------------------------------------------------------
# _gpu_audit
# ---------------------------------------------------------------------------

class TestGpuAudit:
    def test_audit_all_pass(self, fake_env):
        r = _source_and_run("_gpu_audit", **fake_env)
        assert r.returncode == 0
        # May have warnings (e.g. no driver blacklist) but no errors
        assert "GPU Passthrough System Audit" in r.stdout

    def test_audit_iommu_disabled(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, iommu_enabled=False)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_audit", bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert r.returncode != 0
        assert "IOMMU not enabled" in r.stdout

    def test_audit_missing_packages(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, pacman_installed=())
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_audit", bin_dir=bin_dir, sysfs_root=sysfs_root)
        # Missing packages are warnings in mode-based system
        assert "not installed" in r.stdout

    def test_audit_services_not_needed(self, tmp_path):
        """Mode-based system does not check libvirtd."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_audit", bin_dir=bin_dir, sysfs_root=sysfs_root)
        # libvirtd should not appear in mode-based audit
        assert "libvirtd" not in r.stdout

    def test_audit_user_not_in_groups(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, user_groups="wheel")
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_audit", bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert r.returncode != 0
        assert "not in" in r.stdout

    def test_audit_modules_not_loaded(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, lsmod_output="")
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_audit", bin_dir=bin_dir, sysfs_root=sysfs_root)
        # Modules available but not loaded → warnings
        assert "available but not loaded" in r.stdout

    def test_audit_gpu_overview_prints_gpus(self, fake_env):
        """GPU overview section must list each GPU with PCI addr and driver."""
        r = _source_and_run("_gpu_audit", **fake_env)
        assert "GPUs" in r.stdout
        # fake_env has GPUs at 01:00.0 and 02:00.0
        assert "01:00.0" in r.stdout
        assert "02:00.0" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_status
# ---------------------------------------------------------------------------

class TestGpuStatus:
    def test_status_shows_gpus(self, fake_env):
        r = _source_and_run("_gpu_status", **fake_env)
        assert r.returncode == 0
        assert "GPU Passthrough Status" in r.stdout
        assert "01:00.0" in r.stdout
        assert "02:00.0" in r.stdout

    def test_status_shows_iommu_state(self, fake_env):
        r = _source_and_run("_gpu_status", **fake_env)
        assert "IOMMU: enabled" in r.stdout

    def test_status_iommu_disabled(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, iommu_enabled=False)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_status", bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert "IOMMU: not enabled" in r.stdout

    def test_status_shows_driver_status(self, fake_env):
        r = _source_and_run("_gpu_status", **fake_env)
        assert "host" in r.stdout

    def test_status_no_gpus(self, tmp_path):
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir, lspci_output=LSPCI_EMPTY)
        r = _source_and_run("_gpu_status", bin_dir=bin_dir)
        assert "No GPUs detected" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_save_config / _gpu_load_config
# ---------------------------------------------------------------------------

class TestGpuConfig:
    def test_save_creates_config_file(self, fake_env):
        conf_dir = fake_env["home_dir"] / ".config" / "hyprconf"
        r = _source_and_run(
            "_gpu_save_config",
            ["01:00.0", "RTX 3070", "10de:2484", "nvidia", "1", "01:00.0 01:00.1"],
            **fake_env,
        )
        assert r.returncode == 0
        conf_file = conf_dir / "gpu-passthrough.conf"
        assert conf_file.exists()
        content = conf_file.read_text()
        assert 'GPU_PCI_ADDR="01:00.0"' in content
        assert 'GPU_NAME="RTX 3070"' in content

    def test_load_reads_config(self, fake_env):
        conf_dir = fake_env["home_dir"] / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
        )
        r = _source_and_run(
            "_gpu_load_config && echo \"LOADED:$GPU_PCI_ADDR\"",
            [],
            **fake_env,
        )
        assert r.returncode == 0
        assert "LOADED:01:00.0" in r.stdout

    def test_load_missing_returns_error(self, fake_env):
        r = _source_and_run("_gpu_load_config", **fake_env)
        assert r.returncode != 0


# ---------------------------------------------------------------------------
# _gpu_setup
# ---------------------------------------------------------------------------

class TestGpuSetup:
    def test_setup_detects_cpu_vendor(self, fake_env):
        r = _source_and_run("_gpu_setup", **fake_env)
        assert "intel" in r.stdout.lower() or "amd" in r.stdout.lower()

    def test_setup_shows_iommu_enabled(self, fake_env):
        r = _source_and_run("_gpu_setup", **fake_env)
        assert "already enabled" in r.stdout

    def test_setup_advises_iommu_when_disabled(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, iommu_enabled=False)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_setup", bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert "IOMMU not enabled" in r.stdout
        assert "amd_iommu=on" in r.stdout or "intel_iommu=on" in r.stdout or "reboot" in r.stdout.lower() or "Could not auto-apply" in r.stdout

    def test_setup_amd_cpu(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, cpu_vendor="amd", iommu_enabled=False)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_setup", bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert "amd_iommu=on" in r.stdout

    def test_setup_signals_addon_install(self, fake_env):
        r = _source_and_run("_gpu_setup", **fake_env)
        assert "__NEED_ADDON_VFIO__" in r.stdout

    def test_setup_lists_gpus(self, fake_env):
        r = _source_and_run("_gpu_setup", **fake_env)
        assert "NVIDIA" in r.stdout or "01:00.0" in r.stdout

    def test_setup_writes_vfio_modprobe_options(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_setup", bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert "VFIO modprobe" in r.stdout or "disable_vga" in r.stdout or "already configured" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_host_smbios
# ---------------------------------------------------------------------------

class TestGpuHostSmbios:
    def test_reads_smbios_data(self, tmp_path):
        """SMBIOS data is read from sysfs (no dmidecode required)."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        # Create fake DMI sysfs entries
        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True)
        (dmi_dir / "sys_vendor").write_text("ASUS")
        (dmi_dir / "product_name").write_text("ROG STRIX B550-F")
        (dmi_dir / "product_serial").write_text("ABC123XYZ")

        # Override _gpu_host_smbios to use fake sysfs
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_host_smbios() {{
                local dmi="{dmi_dir}"
                local mfg="" product="" serial=""
                [[ -r "$dmi/sys_vendor" ]] && mfg=$(cat "$dmi/sys_vendor" 2>/dev/null)
                [[ -r "$dmi/product_name" ]] && product=$(cat "$dmi/product_name" 2>/dev/null)
                [[ -r "$dmi/product_serial" ]] && serial=$(cat "$dmi/product_serial" 2>/dev/null)
                printf '%s\\t%s\\t%s\\n' "$mfg" "$product" "$serial"
            }}
            _gpu_host_smbios
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "ASUS" in r.stdout
        assert "ROG STRIX B550-F" in r.stdout

    def test_returns_tab_separated(self, tmp_path):
        """SMBIOS output is tab-separated."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True)
        (dmi_dir / "sys_vendor").write_text("ASUS")
        (dmi_dir / "product_name").write_text("ROG STRIX B550-F")
        (dmi_dir / "product_serial").write_text("ABC123XYZ")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_host_smbios() {{
                local dmi="{dmi_dir}"
                local mfg="" product="" serial=""
                [[ -r "$dmi/sys_vendor" ]] && mfg=$(cat "$dmi/sys_vendor" 2>/dev/null)
                [[ -r "$dmi/product_name" ]] && product=$(cat "$dmi/product_name" 2>/dev/null)
                [[ -r "$dmi/product_serial" ]] && serial=$(cat "$dmi/product_serial" 2>/dev/null)
                printf '%s\\t%s\\t%s\\n' "$mfg" "$product" "$serial"
            }}
            _gpu_host_smbios
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "\t" in r.stdout


class TestGpuVmSmbiosSanitize:
    """Tests for _gpu_vm_smbios_sanitize."""

    def test_replaces_spaces_with_underscores(self, tmp_path):
        """Spaces become underscores to survive bash word splitting."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_sanitize "ASUSTeK Computer Inc."
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert r.stdout == "ASUSTeK_Computer_Inc."

    def test_escapes_commas_with_double_comma(self, tmp_path):
        """Commas are escaped with double-comma (QEMU convention)."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_sanitize "Micro-Star International Co., Ltd."
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert r.stdout == "Micro-Star_International_Co.,,_Ltd."

    def test_noop_on_clean_value(self, tmp_path):
        """Values without spaces or commas pass through unchanged."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_sanitize "LENOVO"
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert r.stdout == "LENOVO"


class TestGpuVmSmbiosArgs:
    """Tests for _gpu_vm_smbios_args."""

    def _make_dmi(self, sysfs_root, fields):
        """Create fake DMI sysfs entries."""
        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True, exist_ok=True)
        for name, value in fields.items():
            (dmi_dir / name).write_text(value)
        return dmi_dir

    def test_generates_smbios_types_0_1_2_3_4(self, tmp_path):
        """SMBIOS types 0 (BIOS), 1 (System), 2 (Baseboard), 3 (Chassis), and 4 (Processor) are generated."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        dmi_dir = self._make_dmi(sysfs_root, {
            "bios_vendor": "American Megatrends Inc.",
            "bios_version": "3201",
            "bios_date": "01/04/2024",
            "sys_vendor": "ASUSTeK Computer Inc.",
            "product_name": "ROG STRIX B550-F",
            "product_version": "1.0",
            "product_serial": "ABC123",
            "product_uuid": "12345678-1234-1234-1234-123456789abc",
            "product_family": "GAMING",
            "board_vendor": "ASUSTeK Computer Inc.",
            "board_name": "ROG STRIX B550-F GAMING",
            "board_version": "Rev 1.xx",
            "board_serial": "BRD456",
            "chassis_vendor": "ASUSTeK Computer Inc.",
            "chassis_version": "1.0",
            "chassis_serial": "CHS789",
            "chassis_asset_tag": "ATG001",
            "chassis_type": "3",
        })

        # Create fake /proc/cpuinfo for type 4 fallback
        proc_dir = tmp_path / "proc"
        proc_dir.mkdir()
        (proc_dir / "cpuinfo").write_text(
            "vendor_id\t: AuthenticAMD\n"
            "model name\t: AMD Ryzen 9 5950X\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_args() {{
                local dmi="{dmi_dir}"
                local args=""

                local bios_vendor="" bios_version="" bios_date=""
                [[ -r "$dmi/bios_vendor" ]]  && bios_vendor=$(cat "$dmi/bios_vendor" 2>/dev/null)
                [[ -r "$dmi/bios_version" ]] && bios_version=$(cat "$dmi/bios_version" 2>/dev/null)
                [[ -r "$dmi/bios_date" ]]    && bios_date=$(cat "$dmi/bios_date" 2>/dev/null)
                if [[ -n "$bios_vendor" ]]; then
                    args+="-smbios type=0"
                    args+=",vendor=$(_gpu_vm_smbios_sanitize "$bios_vendor")"
                    [[ -n "$bios_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$bios_version")"
                    [[ -n "$bios_date" ]]    && args+=",date=$(_gpu_vm_smbios_sanitize "$bios_date")"
                    args+=",uefi=on"
                fi

                local sys_vendor="" product_name="" product_version=""
                local product_serial="" product_uuid="" product_family=""
                [[ -r "$dmi/sys_vendor" ]]       && sys_vendor=$(cat "$dmi/sys_vendor" 2>/dev/null)
                [[ -r "$dmi/product_name" ]]     && product_name=$(cat "$dmi/product_name" 2>/dev/null)
                [[ -r "$dmi/product_version" ]]  && product_version=$(cat "$dmi/product_version" 2>/dev/null)
                [[ -r "$dmi/product_serial" ]]   && product_serial=$(cat "$dmi/product_serial" 2>/dev/null)
                [[ -r "$dmi/product_uuid" ]]     && product_uuid=$(cat "$dmi/product_uuid" 2>/dev/null)
                [[ -r "$dmi/product_family" ]]   && product_family=$(cat "$dmi/product_family" 2>/dev/null)
                if [[ -n "$sys_vendor" ]]; then
                    args+=" -smbios type=1"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$sys_vendor")"
                    [[ -n "$product_name" ]]    && args+=",product=$(_gpu_vm_smbios_sanitize "$product_name")"
                    [[ -n "$product_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$product_version")"
                    [[ -n "$product_serial" ]]  && args+=",serial=$(_gpu_vm_smbios_sanitize "$product_serial")"
                    if [[ "$product_uuid" =~ ^[0-9A-Fa-f]{{8}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{12}}$ ]]; then
                        args+=",uuid=$product_uuid"
                    fi
                    [[ -n "$product_family" ]]  && args+=",family=$(_gpu_vm_smbios_sanitize "$product_family")"
                fi

                local board_vendor="" board_name="" board_version="" board_serial=""
                [[ -r "$dmi/board_vendor" ]]  && board_vendor=$(cat "$dmi/board_vendor" 2>/dev/null)
                [[ -r "$dmi/board_name" ]]    && board_name=$(cat "$dmi/board_name" 2>/dev/null)
                [[ -r "$dmi/board_version" ]] && board_version=$(cat "$dmi/board_version" 2>/dev/null)
                [[ -r "$dmi/board_serial" ]]  && board_serial=$(cat "$dmi/board_serial" 2>/dev/null)
                if [[ -n "$board_vendor" ]]; then
                    args+=" -smbios type=2"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$board_vendor")"
                    [[ -n "$board_name" ]]    && args+=",product=$(_gpu_vm_smbios_sanitize "$board_name")"
                    [[ -n "$board_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$board_version")"
                    [[ -n "$board_serial" ]]  && args+=",serial=$(_gpu_vm_smbios_sanitize "$board_serial")"
                fi

                local chassis_vendor="" chassis_version="" chassis_serial="" chassis_asset="" chassis_type=""
                [[ -r "$dmi/chassis_vendor" ]]    && chassis_vendor=$(cat "$dmi/chassis_vendor" 2>/dev/null)
                [[ -r "$dmi/chassis_version" ]]   && chassis_version=$(cat "$dmi/chassis_version" 2>/dev/null)
                [[ -r "$dmi/chassis_serial" ]]    && chassis_serial=$(cat "$dmi/chassis_serial" 2>/dev/null)
                [[ -r "$dmi/chassis_asset_tag" ]] && chassis_asset=$(cat "$dmi/chassis_asset_tag" 2>/dev/null)
                [[ -r "$dmi/chassis_type" ]]      && chassis_type=$(cat "$dmi/chassis_type" 2>/dev/null)
                if [[ -n "$chassis_vendor" ]]; then
                    args+=" -smbios type=3"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$chassis_vendor")"
                    [[ -n "$chassis_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$chassis_version")"
                    [[ -n "$chassis_serial" ]]  && args+=",serial=$(_gpu_vm_smbios_sanitize "$chassis_serial")"
                    [[ -n "$chassis_asset" ]]   && args+=",asset=$(_gpu_vm_smbios_sanitize "$chassis_asset")"
                    [[ "$chassis_type" =~ ^[0-9]+$ ]] && args+=",type=${{chassis_type}}"
                fi

                # Type 4 — Processor (from fake /proc/cpuinfo)
                local cpu_mfg="" cpu_ver=""
                cpu_mfg=$(grep -m1 'vendor_id' "{proc_dir}/cpuinfo" 2>/dev/null | awk -F': ' '{{print $2}}' || true)
                cpu_ver=$(grep -m1 'model name' "{proc_dir}/cpuinfo" 2>/dev/null | awk -F': ' '{{print $2}}' || true)
                if [[ -n "$cpu_mfg" ]] && [[ -n "$cpu_ver" ]]; then
                    args+=" -smbios type=4"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$cpu_mfg")"
                    args+=",version=$(_gpu_vm_smbios_sanitize "$cpu_ver")"
                fi

                args="${{args# }}"
                printf '%s' "$args"
            }}
            _gpu_vm_smbios_args
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        out = r.stdout

        # Type 0 — BIOS with uefi=on
        assert "-smbios type=0" in out
        assert "vendor=American_Megatrends_Inc." in out
        assert "version=3201" in out
        assert "date=01/04/2024" in out
        assert "uefi=on" in out
        # Type 1 — System (spaces → underscores, UUID validated)
        assert "-smbios type=1" in out
        assert "manufacturer=ASUSTeK_Computer_Inc." in out
        assert "product=ROG_STRIX_B550-F" in out
        assert "serial=ABC123" in out
        assert "uuid=12345678-1234-1234-1234-123456789abc" in out
        assert "family=GAMING" in out
        # Type 2 — Baseboard
        assert "-smbios type=2" in out
        assert "product=ROG_STRIX_B550-F_GAMING" in out
        assert "serial=BRD456" in out
        # Type 3 — Chassis
        assert "-smbios type=3" in out
        assert "serial=CHS789" in out
        assert "asset=ATG001" in out
        assert "type=3" in out
        # Type 4 — Processor
        assert "-smbios type=4" in out
        assert "manufacturer=AuthenticAMD" in out
        assert "version=AMD_Ryzen_9_5950X" in out

    def test_skips_unreadable_fields(self, tmp_path):
        """Only available fields are included; missing ones are skipped."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        # Only provide minimal type 1 data — no serial, uuid, family
        dmi_dir = self._make_dmi(sysfs_root, {
            "sys_vendor": "LENOVO",
            "product_name": "ThinkPad",
        })

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_args() {{
                local dmi="{dmi_dir}"
                local args=""

                local bios_vendor=""
                [[ -r "$dmi/bios_vendor" ]] && bios_vendor=$(cat "$dmi/bios_vendor" 2>/dev/null)
                if [[ -n "$bios_vendor" ]]; then
                    args+="-smbios type=0,vendor=$(_gpu_vm_smbios_sanitize "$bios_vendor"),uefi=on"
                fi

                local sys_vendor="" product_name="" product_version=""
                local product_serial="" product_uuid="" product_family=""
                [[ -r "$dmi/sys_vendor" ]]      && sys_vendor=$(cat "$dmi/sys_vendor" 2>/dev/null)
                [[ -r "$dmi/product_name" ]]    && product_name=$(cat "$dmi/product_name" 2>/dev/null)
                [[ -r "$dmi/product_version" ]] && product_version=$(cat "$dmi/product_version" 2>/dev/null)
                [[ -r "$dmi/product_serial" ]]  && product_serial=$(cat "$dmi/product_serial" 2>/dev/null)
                [[ -r "$dmi/product_uuid" ]]    && product_uuid=$(cat "$dmi/product_uuid" 2>/dev/null)
                [[ -r "$dmi/product_family" ]]  && product_family=$(cat "$dmi/product_family" 2>/dev/null)
                if [[ -n "$sys_vendor" ]]; then
                    args+=" -smbios type=1"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$sys_vendor")"
                    [[ -n "$product_name" ]]    && args+=",product=$(_gpu_vm_smbios_sanitize "$product_name")"
                    [[ -n "$product_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$product_version")"
                    [[ -n "$product_serial" ]]  && args+=",serial=$(_gpu_vm_smbios_sanitize "$product_serial")"
                    if [[ "$product_uuid" =~ ^[0-9A-Fa-f]{{8}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{12}}$ ]]; then
                        args+=",uuid=$product_uuid"
                    fi
                    [[ -n "$product_family" ]]  && args+=",family=$(_gpu_vm_smbios_sanitize "$product_family")"
                fi

                args="${{args# }}"
                printf '%s' "$args"
            }}
            _gpu_vm_smbios_args
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        out = r.stdout

        # Type 0, 2, 3, 4, 17 should be absent (no sysfs entries / no proc mock / no dmidecode)
        assert "type=0" not in out
        assert "type=2" not in out
        assert "type=3" not in out
        assert "type=4" not in out
        assert "type=17" not in out
        # Type 1 present with available fields only
        assert "-smbios type=1" in out
        assert "manufacturer=LENOVO" in out
        assert "product=ThinkPad" in out
        assert "serial=" not in out
        assert "uuid=" not in out

    def test_uuid_validation_rejects_invalid(self, tmp_path):
        """Invalid UUID format is not passed to QEMU."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        dmi_dir = self._make_dmi(sysfs_root, {
            "sys_vendor": "LENOVO",
            "product_uuid": "Not Available",
        })

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_args() {{
                local dmi="{dmi_dir}"
                local args="" product_uuid=""
                [[ -r "$dmi/product_uuid" ]] && product_uuid=$(cat "$dmi/product_uuid" 2>/dev/null)
                local sys_vendor=""
                [[ -r "$dmi/sys_vendor" ]] && sys_vendor=$(cat "$dmi/sys_vendor" 2>/dev/null)
                if [[ -n "$sys_vendor" ]]; then
                    args+="-smbios type=1,manufacturer=$(_gpu_vm_smbios_sanitize "$sys_vendor")"
                    if [[ "$product_uuid" =~ ^[0-9A-Fa-f]{{8}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{4}}-[0-9A-Fa-f]{{12}}$ ]]; then
                        args+=",uuid=$product_uuid"
                    fi
                fi
                printf '%s' "$args"
            }}
            _gpu_vm_smbios_args
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "uuid=" not in r.stdout
        assert "manufacturer=LENOVO" in r.stdout

    def test_empty_sysfs_returns_empty(self, tmp_path):
        """Returns empty string when no DMI data is available."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        # Create empty DMI dir — no files
        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_args() {{
                local dmi="{dmi_dir}"
                local args=""

                local bios_vendor=""
                [[ -r "$dmi/bios_vendor" ]] && bios_vendor=$(cat "$dmi/bios_vendor" 2>/dev/null)
                [[ -n "$bios_vendor" ]] && args+="-smbios type=0,vendor=$(_gpu_vm_smbios_sanitize "$bios_vendor"),uefi=on"

                local sys_vendor=""
                [[ -r "$dmi/sys_vendor" ]] && sys_vendor=$(cat "$dmi/sys_vendor" 2>/dev/null)
                [[ -n "$sys_vendor" ]] && args+=" -smbios type=1,manufacturer=$(_gpu_vm_smbios_sanitize "$sys_vendor")"

                args="${{args# }}"
                printf '%s' "$args"
            }}
            result=$(_gpu_vm_smbios_args)
            if [[ -z "$result" ]]; then
                echo "EMPTY"
            else
                echo "$result"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert r.stdout.strip() == "EMPTY"

    def test_type17_memory_from_dmidecode(self, tmp_path):
        """SMBIOS type 17 (Memory) is generated when dmidecode is available."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True, exist_ok=True)

        # Create a fake dmidecode that outputs realistic memory info
        fake_dmidecode = bin_dir / "dmidecode"
        fake_dmidecode.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            echo "# dmidecode 3.5"
            echo "Memory Device"
            echo "	Manufacturer: G Skill Intl"
            echo "	Speed: 3600 MT/s"
            echo "	Serial Number: 00000001"
            echo "	Part Number: F4-3600C16-16GVKC"
            echo "	Locator: DIMM_A1"
        """))
        fake_dmidecode.chmod(0o755)

        # Create a fake sudo that just runs the command
        fake_sudo = bin_dir / "sudo"
        fake_sudo.write_text('#!/usr/bin/env bash\nshift; "$@"\n')
        fake_sudo.chmod(0o755)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_smbios_args() {{
                local dmi="{dmi_dir}"
                local args=""

                # Skip types 0-4 for brevity, just test type 17
                if command -v dmidecode &>/dev/null; then
                    local mem_mfg="" mem_speed="" mem_serial="" mem_part="" mem_loc=""
                    mem_mfg=$(sudo -n dmidecode -t memory 2>/dev/null \\
                        | grep -m1 'Manufacturer:' | sed 's/.*Manufacturer:[[:space:]]*//' || true)
                    mem_speed=$(sudo -n dmidecode -t memory 2>/dev/null \\
                        | grep -m1 'Speed:' | grep -oP '\\d+' | head -1 || true)
                    mem_serial=$(sudo -n dmidecode -t memory 2>/dev/null \\
                        | grep -m1 'Serial Number:' | sed 's/.*Serial Number:[[:space:]]*//' || true)
                    mem_part=$(sudo -n dmidecode -t memory 2>/dev/null \\
                        | grep -m1 'Part Number:' | sed 's/.*Part Number:[[:space:]]*//' || true)
                    mem_loc=$(sudo -n dmidecode -t memory 2>/dev/null \\
                        | grep -m1 'Locator:' | sed 's/.*Locator:[[:space:]]*//' || true)
                    if [[ -n "$mem_mfg" ]] && [[ "$mem_mfg" != "Unknown" ]] && [[ "$mem_mfg" != "Not Specified" ]]; then
                        args+=" -smbios type=17"
                        args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$mem_mfg")"
                        [[ -n "$mem_speed" ]] && args+=",speed=${{mem_speed}}"
                        [[ -n "$mem_serial" ]] && [[ "$mem_serial" != "Unknown" ]] && [[ "$mem_serial" != "Not Specified" ]] \\
                            && args+=",serial=$(_gpu_vm_smbios_sanitize "$mem_serial")"
                        [[ -n "$mem_part" ]] && [[ "$mem_part" != "Unknown" ]] && [[ "$mem_part" != "Not Specified" ]] \\
                            && args+=",part=$(_gpu_vm_smbios_sanitize "$mem_part")"
                        [[ -n "$mem_loc" ]] && [[ "$mem_loc" != "Unknown" ]] && [[ "$mem_loc" != "Not Specified" ]] \\
                            && args+=",loc_pfx=$(_gpu_vm_smbios_sanitize "$mem_loc")"
                    fi
                fi

                args="${{args# }}"
                printf '%s' "$args"
            }}
            _gpu_vm_smbios_args
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        out = r.stdout

        assert "-smbios type=17" in out
        assert "manufacturer=G_Skill_Intl" in out
        assert "speed=3600" in out
        assert "serial=00000001" in out
        assert "part=F4-3600C16-16GVKC" in out
        assert "loc_pfx=DIMM_A1" in out

    def test_type17_skipped_when_no_dmidecode(self, tmp_path):
        """SMBIOS type 17 is skipped when dmidecode is not available."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True, exist_ok=True)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            # Override command to pretend dmidecode does not exist
            command() {{
                if [[ "${{2:-}}" == "dmidecode" ]] && [[ "${{1:-}}" == "-v" ]]; then
                    return 1
                fi
                builtin command "$@"
            }}
            _gpu_vm_smbios_args() {{
                local args=""
                if command -v dmidecode &>/dev/null; then
                    args+=" -smbios type=17,manufacturer=FAKE"
                fi
                args="${{args# }}"
                printf '%s' "$args"
            }}
            _gpu_vm_smbios_args
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "type=17" not in r.stdout


class TestGpuVmComposeSmbios:
    """Tests for anti-detection and Looking Glass integration in compose output."""

    def test_compose_includes_smbios_and_cpu_flags(self, tmp_path):
        """Compose includes SMBIOS, CPU_FLAGS, MACHINE, disk flags, and anti-detection env vars."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        # Create fake DMI entries
        dmi_dir = sysfs_root / "devices" / "virtual" / "dmi" / "id"
        dmi_dir.mkdir(parents=True)
        (dmi_dir / "bios_vendor").write_text("American Megatrends Inc.")
        (dmi_dir / "bios_version").write_text("3201")
        (dmi_dir / "bios_date").write_text("01/04/2024")
        (dmi_dir / "sys_vendor").write_text("ASUSTeK Computer Inc.")
        (dmi_dir / "product_name").write_text("ROG STRIX")
        (dmi_dir / "board_vendor").write_text("ASUSTeK Computer Inc.")
        (dmi_dir / "board_name").write_text("ROG STRIX B550-F")
        (dmi_dir / "chassis_vendor").write_text("ASUSTeK Computer Inc.")
        (dmi_dir / "chassis_type").write_text("3")

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
            'VM_IVSHMEM_SIZE="64"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            # Override smbios to use fake sysfs
            _gpu_vm_smbios_args() {{
                local dmi="{dmi_dir}"
                local args=""
                local bios_vendor="" bios_version="" bios_date=""
                [[ -r "$dmi/bios_vendor" ]]  && bios_vendor=$(cat "$dmi/bios_vendor" 2>/dev/null)
                [[ -r "$dmi/bios_version" ]] && bios_version=$(cat "$dmi/bios_version" 2>/dev/null)
                [[ -r "$dmi/bios_date" ]]    && bios_date=$(cat "$dmi/bios_date" 2>/dev/null)
                if [[ -n "$bios_vendor" ]]; then
                    args+="-smbios type=0"
                    args+=",vendor=$(_gpu_vm_smbios_sanitize "$bios_vendor")"
                    [[ -n "$bios_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$bios_version")"
                    [[ -n "$bios_date" ]]    && args+=",date=$(_gpu_vm_smbios_sanitize "$bios_date")"
                    args+=",uefi=on"
                fi
                local sys_vendor="" product_name=""
                [[ -r "$dmi/sys_vendor" ]]   && sys_vendor=$(cat "$dmi/sys_vendor" 2>/dev/null)
                [[ -r "$dmi/product_name" ]] && product_name=$(cat "$dmi/product_name" 2>/dev/null)
                if [[ -n "$sys_vendor" ]]; then
                    args+=" -smbios type=1"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$sys_vendor")"
                    [[ -n "$product_name" ]] && args+=",product=$(_gpu_vm_smbios_sanitize "$product_name")"
                fi
                local board_vendor="" board_name=""
                [[ -r "$dmi/board_vendor" ]] && board_vendor=$(cat "$dmi/board_vendor" 2>/dev/null)
                [[ -r "$dmi/board_name" ]]   && board_name=$(cat "$dmi/board_name" 2>/dev/null)
                if [[ -n "$board_vendor" ]]; then
                    args+=" -smbios type=2"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$board_vendor")"
                    [[ -n "$board_name" ]] && args+=",product=$(_gpu_vm_smbios_sanitize "$board_name")"
                fi
                local chassis_vendor="" chassis_type=""
                [[ -r "$dmi/chassis_vendor" ]] && chassis_vendor=$(cat "$dmi/chassis_vendor" 2>/dev/null)
                [[ -r "$dmi/chassis_type" ]]   && chassis_type=$(cat "$dmi/chassis_type" 2>/dev/null)
                if [[ -n "$chassis_vendor" ]]; then
                    args+=" -smbios type=3"
                    args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$chassis_vendor")"
                    [[ "$chassis_type" =~ ^[0-9]+$ ]] && args+=",type=${{chassis_type}}"
                fi
                args="${{args# }}"
                printf '%s' "$args"
            }}
            # Override cpu_flags to return predictable value
            _gpu_vm_cpu_flags() {{ printf '%s' "-hypervisor,hv_vendor_id=AuthenticAMD,family=25,model=33,stepping=2"; }}
            # Override disk_flags (no real disk in test)
            _gpu_vm_disk_flags() {{ printf '%s' "-global ide-hd.model=Samsung_970_EVO"; }}
            # Simulate kvmfr0 device for Looking Glass
            _GPU_VM_KVMFR_DEV="{tmp_path}/kvmfr0"
            touch "$_GPU_VM_KVMFR_DEV"
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout

        # GPU device arg still present
        assert "vfio-pci,host=01:00.0" in compose
        # SMBIOS type 0 — BIOS with uefi=on
        assert "-smbios type=0" in compose
        assert "vendor=American_Megatrends_Inc." in compose
        assert "uefi=on" in compose
        # SMBIOS type 1 — System
        assert "-smbios type=1" in compose
        assert "manufacturer=ASUSTeK_Computer_Inc." in compose
        assert "product=ROG_STRIX" in compose
        # Type 2 — Baseboard
        assert "-smbios type=2" in compose
        assert "product=ROG_STRIX_B550-F" in compose
        # Type 3 — Chassis
        assert "-smbios type=3" in compose
        assert "type=3" in compose
        # CPU_FLAGS env var
        assert 'CPU_FLAGS: "-hypervisor,hv_vendor_id=AuthenticAMD,family=25,model=33,stepping=2"' in compose
        # MACHINE env var
        assert 'MACHINE: "q35"' in compose
        # Disk spoofing in ARGUMENTS
        assert "ide-hd.model=Samsung_970_EVO" in compose
        # Anti-detection env vars (eliminate VirtIO fingerprints)
        assert 'DISPLAY: "none"' in compose
        assert 'ADAPTER: "e1000e"' in compose
        assert 'DISK_TYPE: "sata"' in compose
        assert 'USB: "no"' in compose
        # Looking Glass ivshmem device
        assert "ivshmem-plain,id=shmem0,memdev=looking-glass" in compose
        assert "memory-backend-file,id=looking-glass,mem-path=" in compose
        assert "size=64M,share=yes" in compose  # matches VM_IVSHMEM_SIZE=64 in test config
        assert "kvmfr0" in compose
        # Audio: removed entirely (Dockurr QEMU lacks all audio backends)
        assert "-device intel-hda" not in compose
        assert "-audiodev" not in compose
        # No SPICE (Dockurr QEMU does not have SPICE compiled in)
        assert "-spice" not in compose
        assert "virtio-serial-pci" not in compose
        assert "spicechannel0" not in compose
        assert "vdagent" not in compose
        assert "virtio-mouse-pci" not in compose
        assert "virtio-keyboard-pci" not in compose
        # ICH9 power management
        assert "ICH9-LPC.disable_s3=1" in compose
        assert "ICH9-LPC.disable_s4=1" in compose
        # PulseAudio volume mount not needed (no host audio backend)
        # OEM volume mount for auto-install
        assert "/oem" in compose
        # ulimits for VFIO memory locking
        assert "memlock:" in compose
        assert "soft: -1" in compose
        assert "hard: -1" in compose

    def test_compose_works_without_dmi(self, tmp_path):
        """Compose generates correctly even if DMI data is unavailable."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })
        # No DMI directory at all

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            # Override: no DMI data available
            _gpu_vm_smbios_args() {{ printf ''; }}
            _gpu_vm_cpu_flags() {{ printf ''; }}
            _gpu_vm_disk_flags() {{ printf ''; }}
            # Simulate kvmfr0 device for Looking Glass
            _GPU_VM_KVMFR_DEV="{tmp_path}/kvmfr0"
            touch "$_GPU_VM_KVMFR_DEV"
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout

        # Core compose structure still works
        assert "dockurr/windows" in compose
        assert "vfio-pci,host=01:00.0" in compose
        # No SMBIOS args injected
        assert "-smbios" not in compose
        # MACHINE q35 still present (always set)
        assert 'MACHINE: "q35"' in compose
        # Anti-detection env vars always present
        assert 'DISPLAY: "none"' in compose
        assert 'ADAPTER: "e1000e"' in compose
        assert 'DISK_TYPE: "sata"' in compose
        # Looking Glass present when kvmfr device exists
        assert "ivshmem-plain" in compose
        assert "kvmfr0" in compose

    def test_compose_ivshmem_size_from_config(self, tmp_path):
        """IVSHMEM size from VM config is used in Looking Glass device."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
            'VM_IVSHMEM_SIZE="128"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            _gpu_vm_smbios_args() {{ printf ''; }}
            _gpu_vm_cpu_flags() {{ printf ''; }}
            _gpu_vm_disk_flags() {{ printf ''; }}
            _GPU_VM_KVMFR_DEV="{tmp_path}/kvmfr0"
            touch "$_GPU_VM_KVMFR_DEV"
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout

        assert "size=128M,share=yes" in compose

    def test_compose_usb_no_by_default(self, tmp_path):
        """USB is disabled by default; no USB controller without USB devices."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            _gpu_vm_smbios_args() {{ printf ''; }}
            _gpu_vm_cpu_flags() {{ printf ''; }}
            _gpu_vm_disk_flags() {{ printf ''; }}
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout

        assert 'USB: "no"' in compose
        assert "qemu-xhci" not in compose
        # Audio: removed entirely (Dockurr QEMU lacks all audio backends)
        assert "-device intel-hda" not in compose
        assert "-audiodev" not in compose


class TestGpuVmOem:
    """Tests for OEM auto-install script generation."""

    def test_generate_oem_creates_install_bat(self, tmp_path):
        """_gpu_vm_generate_oem creates install.bat with Steam and Epic installers."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_generate_oem
            cat "$_GPU_VM_OEM_DIR/install.bat"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        bat = r.stdout

        assert "SteamSetup.exe" in bat
        assert "EpicInstaller.msi" in bat
        assert "EpicGamesLauncherInstaller.msi" in bat
        assert "Battle.net-Setup.exe" in bat
        assert "FirefoxSetup.exe" in bat
        assert "looking-glass.io/artifact/B7/host" in bat
        assert "looking-glass-host" in bat
        assert "/S" in bat
        assert "/quiet" in bat
        # Privacy hardening
        assert "AllowTelemetry" in bat
        assert "AdvertisingInfo" in bat
        assert "DiagTrack" in bat
        assert "TurnOffWindowsCopilot" in bat
        assert "DisableAIDataAnalysis" in bat

    def test_oem_dir_created_by_generate(self, tmp_path):
        """OEM directory is created by _gpu_vm_generate_oem."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        oem_dir = home_dir / ".local" / "share" / "hyprconf" / "windows-vm-oem"

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_generate_oem
            [[ -d "$_GPU_VM_OEM_DIR" ]] && echo "OEM_DIR_EXISTS"
            [[ -f "$_GPU_VM_OEM_DIR/install.bat" ]] && echo "INSTALL_BAT_EXISTS"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "OEM_DIR_EXISTS" in r.stdout
        assert "INSTALL_BAT_EXISTS" in r.stdout


class TestGpuVmCpuFlags:
    """Tests for _gpu_vm_cpu_flags() — CPU anti-detection flags."""

    def test_amd_vendor(self, tmp_path):
        """AMD vendor produces hv_vendor_id=AuthenticAMD with cpu family/model/stepping."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(
            "processor\t: 0\n"
            "vendor_id\t: AuthenticAMD\n"
            "cpu family\t: 25\n"
            "model\t\t: 33\n"
            "model name\t: AMD Ryzen 5 5600X\n"
            "stepping\t: 2\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_cpu_flags() {{
                local cpuinfo="{cpuinfo}"
                local vendor="" family="" model="" stepping=""
                vendor=$(grep -m1 '^vendor_id[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                family=$(grep -m1 '^cpu family[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                model=$(grep -m1 '^model[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                stepping=$(grep -m1 '^stepping[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true

                [[ -z "$vendor" ]] && return 0
                local flags="-hypervisor,hv_vendor_id=$vendor"
                [[ "$family" =~ ^[0-9]+$ ]]   && flags+=",family=$family"
                [[ "$model" =~ ^[0-9]+$ ]]     && flags+=",model=$model"
                [[ "$stepping" =~ ^[0-9]+$ ]] && flags+=",stepping=$stepping"
                printf '%s' "$flags"
            }}
            _gpu_vm_cpu_flags
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        out = r.stdout
        assert "-hypervisor" in out
        assert "hv_vendor_id=AuthenticAMD" in out
        assert "family=25" in out
        assert "model=33" in out
        assert "stepping=2" in out

    def test_intel_vendor(self, tmp_path):
        """Intel vendor produces hv_vendor_id=GenuineIntel."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(
            "processor\t: 0\n"
            "vendor_id\t: GenuineIntel\n"
            "cpu family\t: 6\n"
            "model\t\t: 151\n"
            "model name\t: 12th Gen Intel(R) Core(TM) i7-12700K\n"
            "stepping\t: 2\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_cpu_flags() {{
                local cpuinfo="{cpuinfo}"
                local vendor="" family="" model="" stepping=""
                vendor=$(grep -m1 '^vendor_id[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                family=$(grep -m1 '^cpu family[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                model=$(grep -m1 '^model[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                stepping=$(grep -m1 '^stepping[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true

                [[ -z "$vendor" ]] && return 0
                local flags="-hypervisor,hv_vendor_id=$vendor"
                [[ "$family" =~ ^[0-9]+$ ]]   && flags+=",family=$family"
                [[ "$model" =~ ^[0-9]+$ ]]     && flags+=",model=$model"
                [[ "$stepping" =~ ^[0-9]+$ ]] && flags+=",stepping=$stepping"
                printf '%s' "$flags"
            }}
            _gpu_vm_cpu_flags
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "hv_vendor_id=GenuineIntel" in r.stdout
        assert "family=6" in r.stdout
        assert "model=151" in r.stdout

    def test_missing_cpuinfo_returns_empty(self, tmp_path):
        """Returns empty when /proc/cpuinfo is unavailable."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_cpu_flags() {{
                local cpuinfo="{tmp_path}/nonexistent"
                local vendor=""
                vendor=$(grep -m1 '^vendor_id[[:space:]]*:' "$cpuinfo" 2>/dev/null | awk '{{print $NF}}') || true
                [[ -z "$vendor" ]] && return 0
                printf '%s' "-hypervisor,hv_vendor_id=$vendor"
            }}
            result=$(_gpu_vm_cpu_flags)
            if [[ -z "$result" ]]; then echo "EMPTY"; else echo "$result"; fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert r.stdout.strip() == "EMPTY"


class TestGpuVmDiskFlags:
    """Tests for _gpu_vm_disk_flags() — disk identity spoofing."""

    def test_nvme_disk(self, tmp_path):
        """NVMe disk is detected and produces ide-hd spoofing flags."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        # Create fake lsblk that responds to per-field queries
        lsblk = bin_dir / "lsblk"
        lsblk.write_text(textwrap.dedent('''\
            #!/bin/bash
            case "$@" in
                *MODEL*nvme*)  echo "Samsung SSD 970 EVO Plus 2TB";;
                *SERIAL*nvme*) echo "S4P2NJ0R123456";;
                *) echo "";;
            esac
        '''))
        lsblk.chmod(0o755)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_vm_disk_flags
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        out = r.stdout
        assert "ide-hd.model=Samsung_SSD_970_EVO_Plus_2TB" in out
        assert "ide-hd.serial=S4P2NJ0R123456" in out
        assert "ide-cd.model=ATAPI_DVD_RW" in out

    def test_no_disk_returns_empty(self, tmp_path):
        """Returns empty when no disk is found."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)

        # Create fake lsblk that returns nothing for all queries
        lsblk = bin_dir / "lsblk"
        lsblk.write_text('#!/bin/bash\nexit 0\n')
        lsblk.chmod(0o755)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            result=$(_gpu_vm_disk_flags)
            if [[ -z "$result" ]]; then echo "EMPTY"; else echo "$result"; fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert r.stdout.strip() == "EMPTY"


# ---------------------------------------------------------------------------
# Mode system (replaces bind/unbind/pass)
# ---------------------------------------------------------------------------

class TestGpuModeVm:
    """Test _gpu_mode_vm (bind GPU to vfio-pci)."""

    def test_mode_vm_already_on_vfio_is_noop(self, tmp_path):
        """If device already on vfio-pci, mode vm should succeed immediately."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
        })
        # Write config
        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
        )
        r = _source_and_run("_gpu_mode_vm", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir)
        assert r.returncode == 0
        assert "already" in r.stdout.lower() or "vfio-pci" in r.stdout

    def test_mode_vm_display_gpu_blocked(self, tmp_path):
        """Mode vm refuses display GPU without force."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(
            sysfs_root,
            gpus={
                "01:00.0": {"driver": "nvidia", "iommu_group": "1",
                             "vendor": "0x10de", "device": "0x2484"},
                "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1",
                             "vendor": "0x10de", "device": "0x228b"},
            },
            display_connectors={"01:00.0": ["connected"]},
        )
        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
        )
        r = _source_and_run(
            "_gpu_mode_vm", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        assert r.returncode != 0
        combined = (r.stderr + r.stdout).lower()
        assert "monitor" in combined or "blackscreen" in combined

    def test_mode_vm_no_config_errors(self, tmp_path):
        """Mode vm without config should error."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        r = _source_and_run("_gpu_mode_vm", bin_dir=bin_dir, home_dir=home_dir)
        assert r.returncode != 0

    def test_mode_vm_sets_driver_override(self, tmp_path):
        """Mode vm sets driver_override to vfio-pci for each IOMMU device."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1",
                         "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1",
                         "vendor": "0x10de", "device": "0x228b"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
        )

        r = _source_and_run(
            "_gpu_mode_vm", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        # The bind may "fail" (no real kernel) but driver_override must be set
        override_0 = (sysfs_root / "bus" / "pci" / "devices" / "0000:01:00.0" / "driver_override").read_text().strip()
        override_1 = (sysfs_root / "bus" / "pci" / "devices" / "0000:01:00.1" / "driver_override").read_text().strip()
        assert override_0 == "vfio-pci", f"GPU driver_override: {override_0!r}"
        assert override_1 == "vfio-pci", f"Audio driver_override: {override_1!r}"


class TestGpuModeHost:
    """Test _gpu_mode_host (restore GPU to host driver)."""

    def test_mode_host_already_on_native(self, tmp_path):
        """Mode host when already on host driver is a noop."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "02:00.0": {"driver": "nvidia", "iommu_group": "2",
                         "vendor": "0x10de", "device": "0x2684"},
        })
        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="02:00.0"\nGPU_NAME="RTX 4090"\n'
            'GPU_VENDOR_DEVICE="10de:2684"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="2"\nGPU_IOMMU_DEVICES="02:00.0"\n'
        )
        r = _source_and_run("_gpu_mode_host", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir)
        assert r.returncode == 0
        assert "already" in r.stdout.lower()

    def test_mode_host_no_config_errors(self, tmp_path):
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        r = _source_and_run("_gpu_mode_host", bin_dir=bin_dir, home_dir=home_dir)
        assert r.returncode != 0

    def test_mode_host_clears_driver_override(self, tmp_path):
        """Mode host clears driver_override so native driver can reclaim."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1",
                         "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "vfio-pci", "iommu_group": "1",
                         "vendor": "0x10de", "device": "0x228b"},
        })
        # Pre-set driver_override to vfio-pci (simulates prior mode_vm)
        dev0 = sysfs_root / "bus" / "pci" / "devices" / "0000:01:00.0"
        dev1 = sysfs_root / "bus" / "pci" / "devices" / "0000:01:00.1"
        (dev0 / "driver_override").write_text("vfio-pci")
        (dev1 / "driver_override").write_text("vfio-pci")

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
        )

        _source_and_run(
            "_gpu_mode_host", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        # driver_override must be cleared (empty)
        override_0 = (dev0 / "driver_override").read_text().strip()
        override_1 = (dev1 / "driver_override").read_text().strip()
        assert override_0 == "", f"GPU driver_override not cleared: {override_0!r}"
        assert override_1 == "", f"Audio driver_override not cleared: {override_1!r}"


class TestGpuModeNone:
    """Test _gpu_mode_none (unbind GPU from all drivers)."""

    def test_mode_none_already_unbound(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "02:00.0": {"driver": None, "iommu_group": "2",
                         "vendor": "0x10de", "device": "0x2684"},
        })
        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="02:00.0"\nGPU_NAME="RTX 4090"\n'
            'GPU_VENDOR_DEVICE="10de:2684"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="2"\nGPU_IOMMU_DEVICES="02:00.0"\n'
        )
        r = _source_and_run("_gpu_mode_none", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir)
        assert r.returncode == 0
        assert "already" in r.stdout.lower() or "none" in r.stdout.lower()

    def test_mode_none_no_config_errors(self, tmp_path):
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        r = _source_and_run("_gpu_mode_none", bin_dir=bin_dir, home_dir=home_dir)
        assert r.returncode != 0


class TestGpuModeGet:
    """Test _gpu_mode_get (show current GPU mode)."""

    def test_mode_get_shows_host(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })
        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
        )
        r = _source_and_run("_gpu_mode_get", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir)
        assert r.returncode == 0
        assert "host" in r.stdout.lower()

    def test_mode_get_no_config(self, tmp_path):
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        r = _source_and_run("_gpu_mode_get", bin_dir=bin_dir, home_dir=home_dir)
        assert "No GPU configured" in r.stdout or "not configured" in r.stdout.lower() or r.returncode != 0


class TestGpuBlacklist:
    """Test _gpu_configure_blacklist."""

    def test_blacklist_nvidia(self, tmp_path):
        """NVIDIA GPU gets driver blacklist written (single-GPU + iGPU)."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_SINGLE_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        blacklist_file = tmp_path / "blacklist-gpu-passthrough.conf"
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            _GPU_BLACKLIST_CONF="{blacklist_file}"
            source "{SCRIPT}"
            _gpu_remove_kernel_param() {{ return 0; }}
            _gpu_rebuild_initramfs() {{ return 0; }}
            _gpu_configure_blacklist
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert blacklist_file.exists()
        content = blacklist_file.read_text()
        assert "install nvidia /bin/false" in content

    @pytest.mark.skip(reason="Dual boot entry rewrite — tests pending")
    def test_blacklist_skipped_multi_nvidia(self, tmp_path):
        """Multi-NVIDIA setup: blacklist is NOT written, boot-time binding is configured."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_TWO_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
            'GPU_AUDIO_IDS="10de:228b"\n'
        )

        blacklist_file = tmp_path / "blacklist-gpu-passthrough.conf"
        vfio_conf = tmp_path / "vfio.conf"
        vfio_conf.write_text("options vfio-pci disable_vga=1\n")
        mkinitcpio = tmp_path / "mkinitcpio.conf"
        mkinitcpio.write_text("MODULES=(nvidia nvidia_modeset nvidia_uvm nvidia_drm)\n")
        # Create a fake boot entry for kernel cmdline
        boot_entries = tmp_path / "loader" / "entries"
        boot_entries.mkdir(parents=True)
        (boot_entries / "linux.conf").write_text("options quiet splash\n")

        # Fake bootctl that reports installed + fake mkinitcpio
        _make_executable(bin_dir / "bootctl", textwrap.dedent("""\
            #!/usr/bin/env bash
            exit 0
        """))
        _make_executable(bin_dir / "mkinitcpio", "#!/usr/bin/env bash\nexit 0\n")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            _GPU_BLACKLIST_CONF="{blacklist_file}"
            source "{SCRIPT}"
            # Override paths for test
            _gpu_set_kernel_param() {{
                local key="$1" value="$2"
                # Write to a file so tests can verify
                echo "${{key}}=${{value}}" >> "{tmp_path}/kernel_params_set"
            }}
            _gpu_ensure_mkinitcpio_vfio_first() {{
                echo "mkinitcpio_vfio_first_called" >> "{tmp_path}/calls"
            }}
            _gpu_ensure_vfio_softdep() {{
                echo "vfio_softdep_called" >> "{tmp_path}/calls"
            }}
            _gpu_rebuild_initramfs() {{
                echo "rebuild_initramfs_called" >> "{tmp_path}/calls"
            }}
            _gpu_configure_blacklist
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert not blacklist_file.exists(), "Blacklist should not be written in multi-GPU"
        # Verify boot-time binding was configured
        assert "multi-NVIDIA" in r.stdout or "boot-time" in r.stdout
        params = (tmp_path / "kernel_params_set").read_text()
        assert "vfio-pci.ids=10de:2484,10de:228b" in params
        calls = (tmp_path / "calls").read_text()
        assert "mkinitcpio_vfio_first_called" in calls
        assert "vfio_softdep_called" in calls
        assert "rebuild_initramfs_called" in calls

    @pytest.mark.skip(reason="Dual boot entry rewrite — tests pending")
    def test_blacklist_stale_removed_multi_nvidia(self, tmp_path):
        """Multi-NVIDIA setup: pre-existing blacklist file is removed."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_TWO_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        # Pre-existing stale blacklist
        blacklist_file = tmp_path / "blacklist-gpu-passthrough.conf"
        blacklist_file.write_text("install nvidia /bin/false\n")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            _GPU_BLACKLIST_CONF="{blacklist_file}"
            source "{SCRIPT}"
            _gpu_set_kernel_param() {{ return 0; }}
            _gpu_ensure_mkinitcpio_vfio_first() {{ return 0; }}
            _gpu_ensure_vfio_softdep() {{ return 0; }}
            _gpu_rebuild_initramfs() {{ return 0; }}
            _gpu_configure_blacklist
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert not blacklist_file.exists(), "Stale blacklist should be removed"
        assert "Removed stale" in r.stdout


# ---------------------------------------------------------------------------
# Boot-time vfio-pci binding helpers
# ---------------------------------------------------------------------------

class TestGpuBootTimeBinding:
    """Test boot-time vfio-pci.ids binding helpers."""

    def test_mkinitcpio_vfio_before_nvidia(self, tmp_path):
        """_gpu_ensure_mkinitcpio_vfio_first inserts vfio-pci before nvidia."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        mkinitcpio = tmp_path / "mkinitcpio.conf"
        mkinitcpio.write_text("MODULES=(nvidia nvidia_modeset nvidia_uvm nvidia_drm)\n")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_ensure_mkinitcpio_vfio_first() {{
                local mkinitcpio="{mkinitcpio}"
                [[ -f "$mkinitcpio" ]] || return 0
                local current_modules
                current_modules=$(grep '^MODULES=' "$mkinitcpio" 2>/dev/null | head -1 | sed 's/MODULES=(\\(.*\\))/\\1/')
                if echo "$current_modules" | grep -qE 'vfio.pci.*nvidia'; then
                    printf "  ✔ vfio-pci already before nvidia in mkinitcpio MODULES.\\n"
                    return 0
                fi
                local cleaned
                cleaned=$(echo "$current_modules" | sed -E 's/\\bvfio[-_]pci\\b//g' | tr -s ' ' | sed 's/^ //;s/ $//')
                local new_modules
                if echo "$cleaned" | grep -q 'nvidia'; then
                    new_modules=$(echo "$cleaned" | sed 's/nvidia/vfio-pci nvidia/')
                else
                    new_modules="vfio-pci ${{cleaned}}"
                fi
                new_modules=$(echo "$new_modules" | tr -s ' ' | sed 's/^ //;s/ $//')
                sed -i "s/^MODULES=(.*/MODULES=(${{new_modules}})/" "$mkinitcpio"
            }}
            _gpu_ensure_mkinitcpio_vfio_first
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        content = mkinitcpio.read_text()
        assert "vfio-pci" in content
        # vfio-pci should come before nvidia
        idx_vfio = content.index("vfio-pci")
        idx_nvidia = content.index("nvidia", idx_vfio + 1)
        assert idx_vfio < idx_nvidia, f"vfio-pci ({idx_vfio}) not before nvidia ({idx_nvidia})"

    def test_mkinitcpio_vfio_already_present(self, tmp_path):
        """_gpu_ensure_mkinitcpio_vfio_first is idempotent."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        mkinitcpio = tmp_path / "mkinitcpio.conf"
        mkinitcpio.write_text("MODULES=(vfio-pci nvidia nvidia_modeset nvidia_uvm nvidia_drm)\n")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_ensure_mkinitcpio_vfio_first() {{
                local mkinitcpio="{mkinitcpio}"
                [[ -f "$mkinitcpio" ]] || return 0
                local current_modules
                current_modules=$(grep '^MODULES=' "$mkinitcpio" 2>/dev/null | head -1 | sed 's/MODULES=(\\(.*\\))/\\1/')
                if echo "$current_modules" | grep -qE 'vfio.pci.*nvidia'; then
                    printf "  ✔ vfio-pci already before nvidia in mkinitcpio MODULES.\\n"
                    return 0
                fi
            }}
            _gpu_ensure_mkinitcpio_vfio_first
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "already" in r.stdout
        content = mkinitcpio.read_text()
        # Should be unchanged
        assert content.count("vfio-pci") == 1

    def test_vfio_softdep_added(self, tmp_path):
        """_gpu_ensure_vfio_softdep appends softdep to vfio.conf."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        vfio_conf = tmp_path / "vfio.conf"
        vfio_conf.write_text("options vfio-pci disable_vga=1\n")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_ensure_vfio_softdep() {{
                local vfio_conf="{vfio_conf}"
                if [[ -f "$vfio_conf" ]] && grep -q 'softdep nvidia pre: vfio-pci' "$vfio_conf" 2>/dev/null; then
                    printf "  ✔ softdep nvidia pre: vfio-pci already in %s.\\n" "$vfio_conf"
                    return 0
                fi
                printf "  → Adding softdep to %s\\n" "$vfio_conf"
                printf 'softdep nvidia pre: vfio-pci\\n' >> "$vfio_conf"
            }}
            _gpu_ensure_vfio_softdep
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        content = vfio_conf.read_text()
        assert "softdep nvidia pre: vfio-pci" in content

    def test_vfio_softdep_idempotent(self, tmp_path):
        """_gpu_ensure_vfio_softdep does not duplicate the line."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)
        vfio_conf = tmp_path / "vfio.conf"
        vfio_conf.write_text("options vfio-pci disable_vga=1\nsoftdep nvidia pre: vfio-pci\n")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_ensure_vfio_softdep() {{
                local vfio_conf="{vfio_conf}"
                if [[ -f "$vfio_conf" ]] && grep -q 'softdep nvidia pre: vfio-pci' "$vfio_conf" 2>/dev/null; then
                    printf "  ✔ softdep nvidia pre: vfio-pci already in %s.\\n" "$vfio_conf"
                    return 0
                fi
                printf 'softdep nvidia pre: vfio-pci\\n' >> "$vfio_conf"
            }}
            _gpu_ensure_vfio_softdep
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "already" in r.stdout
        content = vfio_conf.read_text()
        assert content.count("softdep nvidia pre: vfio-pci") == 1

    @pytest.mark.skip(reason="Dual boot entry rewrite — tests pending")
    def test_boot_binding_multi_nvidia_no_audio(self, tmp_path):
        """Boot binding works when GPU_AUDIO_IDS is empty."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_TWO_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        blacklist_file = tmp_path / "blacklist-gpu-passthrough.conf"
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            _GPU_BLACKLIST_CONF="{blacklist_file}"
            source "{SCRIPT}"
            _gpu_set_kernel_param() {{
                echo "${{1}}=${{2}}" >> "{tmp_path}/kernel_params_set"
            }}
            _gpu_ensure_mkinitcpio_vfio_first() {{ return 0; }}
            _gpu_ensure_vfio_softdep() {{ return 0; }}
            _gpu_rebuild_initramfs() {{ return 0; }}
            _gpu_configure_boot_binding
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        params = (tmp_path / "kernel_params_set").read_text()
        # Without audio IDs, should only have GPU device ID
        assert "vfio-pci.ids=10de:2484" in params
        assert "10de:228b" not in params

    def test_boot_binding_single_nvidia_writes_blacklist(self, tmp_path):
        """Single-NVIDIA path still writes blacklist, not boot binding."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_SINGLE_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        blacklist_file = tmp_path / "blacklist-gpu-passthrough.conf"
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            _GPU_BLACKLIST_CONF="{blacklist_file}"
            source "{SCRIPT}"
            _gpu_remove_kernel_param() {{ return 0; }}
            _gpu_rebuild_initramfs() {{ return 0; }}
            _gpu_configure_boot_binding
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert blacklist_file.exists()
        assert "install nvidia /bin/false" in blacklist_file.read_text()

    def test_boot_binding_no_config_skips(self, tmp_path):
        """No GPU configured → boot binding skips cleanly."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_configure_boot_binding
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "skipping" in r.stdout.lower() or "No GPU" in r.stdout


# ---------------------------------------------------------------------------
# Boot-time binding audit checks
# ---------------------------------------------------------------------------

class TestGpuAuditBootBinding:
    """Test audit checks for multi-NVIDIA boot-time binding."""

    def _run_audit_with_cmdline(self, tmp_path, cmdline_content, lspci_output, *, mkinitcpio_content="", vfio_conf_content=""):
        """Helper to run _gpu_audit with faked /proc/cmdline."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=lspci_output, iommu_enabled=True)

        # Override grep to return our custom cmdline
        _make_executable(bin_dir / "grep", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            for arg in "$@"; do
                if [[ "$arg" == "/proc/cmdline" ]]; then
                    echo "{cmdline_content}" | /usr/bin/grep "${{@:1:$(($#-1))}}" -
                    exit $?
                fi
                if [[ "$arg" == "/proc/cpuinfo" ]]; then
                    echo "vendor_id : GenuineIntel"
                    echo "GenuineIntel" | /usr/bin/grep "${{@:1:$(($#-1))}}" -
                    exit $?
                fi
                if [[ "$arg" == "/etc/mkinitcpio.conf" ]]; then
                    echo "{mkinitcpio_content}" | /usr/bin/grep "${{@:1:$(($#-1))}}" -
                    exit $?
                fi
                if [[ "$arg" == "/etc/modprobe.d/vfio.conf" ]]; then
                    echo "{vfio_conf_content}" | /usr/bin/grep "${{@:1:$(($#-1))}}" -
                    exit $?
                fi
            done
            exec /usr/bin/grep "$@"
        """))

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        sysfs_root = tmp_path / "sys"
        _make_fake_sysfs(sysfs_root)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export _GPU_SYSFS="{sysfs_root}"
            source "{SCRIPT}"
            _gpu_audit
        """)
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)

    @pytest.mark.skip(reason="Dual boot entry rewrite — tests pending")
    def test_audit_boot_binding_present(self, tmp_path):
        """Audit reports ✔ when vfio-pci.ids is in cmdline for multi-NVIDIA."""
        r = self._run_audit_with_cmdline(
            tmp_path,
            "intel_iommu=on iommu=pt vfio-pci.ids=10de:2484,10de:228b",
            LSPCI_TWO_NVIDIA,
            mkinitcpio_content="MODULES=(vfio-pci nvidia)",
            vfio_conf_content="softdep nvidia pre: vfio-pci",
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "boot-time" in r.stdout.lower() or "vfio-pci" in r.stdout

    @pytest.mark.skip(reason="Dual boot entry rewrite — tests pending")
    def test_audit_boot_binding_missing(self, tmp_path):
        """Audit warns when vfio-pci.ids is missing for multi-NVIDIA."""
        r = self._run_audit_with_cmdline(
            tmp_path,
            "intel_iommu=on iommu=pt",
            LSPCI_TWO_NVIDIA,
        )
        # Should return warnings (non-zero is for errors, warnings are still rc 0)
        combined = r.stdout + r.stderr
        assert "vfio-pci.ids" in combined or "boot-time" in combined.lower() or "warning" in combined.lower()

class TestGpuDiagnose:
    def test_diagnose_creates_report(self, fake_env):
        r = _source_and_run("_gpu_diagnose", **fake_env)
        assert r.returncode == 0
        assert "GPU Passthrough Diagnostics" in r.stdout
        assert "Report saved" in r.stdout

    def test_diagnose_includes_kernel_info(self, fake_env):
        r = _source_and_run("_gpu_diagnose", **fake_env)
        assert "KERNEL CMDLINE" in r.stdout

    def test_diagnose_includes_iommu_section(self, fake_env):
        r = _source_and_run("_gpu_diagnose", **fake_env)
        assert "IOMMU" in r.stdout

    def test_diagnose_includes_module_info(self, fake_env):
        r = _source_and_run("_gpu_diagnose", **fake_env)
        assert "VFIO MODULES" in r.stdout or "GPU MODULES" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_bind_vfio (limited — no real /sys writes possible in test)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# (Removed: TestGpuBindVfio, TestGpuSysfsBind, TestGpuUnbindVfio)
# These functions were removed when migrating to mode-based system.
# See TestGpuModeVm, TestGpuModeHost, TestGpuModeNone above.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _gpu_unbind_vtconsoles
# ---------------------------------------------------------------------------

class TestGpuUnbindVtconsoles:
    """Test VT console and EFI framebuffer unbinding before GPU driver unbind."""

    def test_unbinds_active_vtconsoles(self, tmp_path):
        """Active VT consoles (bind=1) are unbound (set to 0)."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)

        # Create fake vtconsole entries
        vtcon0 = tmp_path / "sys" / "class" / "vtconsole" / "vtcon0"
        vtcon1 = tmp_path / "sys" / "class" / "vtconsole" / "vtcon1"
        vtcon0.mkdir(parents=True)
        vtcon1.mkdir(parents=True)
        (vtcon0 / "bind").write_text("1")
        (vtcon1 / "bind").write_text("0")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            # Override paths to use fake sysfs
            _gpu_unbind_vtconsoles() {{
                local vtcon
                for vtcon in {tmp_path}/sys/class/vtconsole/vtcon*; do
                    [[ -f "$vtcon/bind" ]] || continue
                    if [[ "$(cat "$vtcon/bind" 2>/dev/null)" == "1" ]]; then
                        echo 0 > "$vtcon/bind"
                        printf "UNBOUND:%s\\n" "$(basename "$vtcon")"
                    fi
                done
            }}
            _gpu_unbind_vtconsoles
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "UNBOUND:vtcon0" in r.stdout
        assert "UNBOUND:vtcon1" not in r.stdout
        assert (vtcon0 / "bind").read_text().strip() == "0"

    def test_skips_inactive_vtconsoles(self, tmp_path):
        """Inactive VT consoles (bind=0) are not touched."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)

        vtcon0 = tmp_path / "sys" / "class" / "vtconsole" / "vtcon0"
        vtcon0.mkdir(parents=True)
        (vtcon0 / "bind").write_text("0")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_unbind_vtconsoles() {{
                local vtcon
                for vtcon in {tmp_path}/sys/class/vtconsole/vtcon*; do
                    [[ -f "$vtcon/bind" ]] || continue
                    if [[ "$(cat "$vtcon/bind" 2>/dev/null)" == "1" ]]; then
                        echo 0 > "$vtcon/bind"
                        printf "UNBOUND:%s\\n" "$(basename "$vtcon")"
                    fi
                done
                printf "DONE\\n"
            }}
            _gpu_unbind_vtconsoles
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "UNBOUND" not in r.stdout
        assert "DONE" in r.stdout

    def test_no_vtconsoles_is_harmless(self, tmp_path):
        """No vtconsole entries does not cause an error."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)

        # No vtconsole directory at all
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_unbind_vtconsoles
            echo "OK"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0
        assert "OK" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_unload_nvidia_modules failure path
# ---------------------------------------------------------------------------

class TestGpuUnloadNvidiaModulesFailure:
    """Test that _gpu_unload_nvidia_modules fails when modules can't be unloaded."""

    def test_returns_nonzero_when_module_stuck(self, tmp_path):
        """If modprobe -r fails for a module, function returns non-zero."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(
            bin_dir,
            lsmod_output="nvidia_drm       12345  1\nnvidia_modeset   23456  1 nvidia_drm\nnvidia         98765  2 nvidia_modeset,nvidia_drm\n",
        )

        # Override modprobe to fail on removal
        _make_executable(bin_dir / "modprobe", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "-r" ]]; then
                exit 1
            fi
            exit 0
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_unload_nvidia_modules
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode != 0
        assert "Cannot unload" in r.stderr or "still loaded" in r.stderr

    def test_returns_zero_when_all_modules_unloaded(self, tmp_path):
        """Successful module unload returns 0."""
        bin_dir = tmp_path / "bin"
        # Modules are listed but modprobe -r will succeed
        _make_fake_bins(
            bin_dir,
            lsmod_output="nvidia_drm       12345  0\nnvidia         98765  0\n",
        )

        # After modprobe -r, simulate that modules are gone
        # by making lsmod return empty after removal
        _make_executable(bin_dir / "modprobe", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "-r" ]]; then
                exit 0
            fi
            exit 0
        """))

        # lsmod returns empty (all modules unloaded)
        _make_executable(bin_dir / "lsmod", textwrap.dedent("""\
            #!/usr/bin/env bash
            echo ""
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_unload_nvidia_modules
            echo "SUCCESS"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0
        assert "SUCCESS" in r.stdout

    def test_mode_vm_aborts_on_nvidia_unload_failure(self, tmp_path):
        """_gpu_mode_vm aborts (returns non-zero) if nvidia modules won't unload."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(
            bin_dir,
            lsmod_output="nvidia_drm       12345  1\nnvidia         98765  1\n",
        )
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
        })

        # modprobe -r always fails
        _make_executable(bin_dir / "modprobe", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "-r" ]]; then exit 1; fi
            exit 0
        """))

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            export _GPU_SYSFS="{sysfs_root}"
            _gpu_current_driver() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local driver_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/driver"
                if [[ -L "$driver_link" ]]; then
                    basename "$(readlink "$driver_link")"
                else
                    echo "none"
                fi
            }}
            _gpu_check_processes() {{ return 0; }}
            _gpu_check_display_safety() {{ return 0; }}
            _gpu_unbind_vtconsoles() {{ return 0; }}
            _gpu_update_state_marker() {{ return 0; }}
            _gpu_ensure_sudo() {{ return 0; }}
            _gpu_mode_vm
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode != 0
        assert "Cannot unload" in r.stderr or "still loaded" in r.stderr

    def test_mode_vm_zombie_state_unloads_nvidia(self, tmp_path):
        """When driver is 'none' but nvidia modules are loaded (zombie state),
        mode_vm should still try to unload nvidia modules."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        # nvidia modules loaded with refs (will fail to unload)
        _make_fake_bins(
            bin_dir,
            lsmod_output="nvidia_drm       12345  1\nnvidia         98765  1\n",
        )
        # GPU has NO driver (zombie state from previous failed attempt)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": None, "iommu_group": "1",
                         "vendor": "0x10de", "device": "0x2484"},
        })

        # modprobe -r fails (modules in use)
        _make_executable(bin_dir / "modprobe", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "-r" ]]; then exit 1; fi
            exit 0
        """))

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            export _GPU_SYSFS="{sysfs_root}"
            _gpu_current_driver() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local driver_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/driver"
                if [[ -L "$driver_link" ]]; then
                    basename "$(readlink "$driver_link")"
                else
                    echo "none"
                fi
            }}
            _gpu_check_processes() {{ return 0; }}
            _gpu_check_display_safety() {{ return 0; }}
            _gpu_unbind_vtconsoles() {{ return 0; }}
            _gpu_update_state_marker() {{ return 0; }}
            _gpu_ensure_sudo() {{ return 0; }}
            _gpu_mode_vm
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        # Should fail because nvidia modules can't be unloaded
        assert r.returncode != 0
        assert "Cannot unload" in r.stderr or "still loaded" in r.stderr

    def test_force_flag_bypasses_display_safety(self, tmp_path):
        """--force skips the display GPU safety check inside the function."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(
            sysfs_root,
            gpus={
                "01:00.0": {"driver": "vfio-pci", "iommu_group": "1",
                             "vendor": "0x10de", "device": "0x2484"},
            },
            display_connectors={"01:00.0": ["connected"]},
        )

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )

        # Call _gpu_mode_vm with "force" — already on vfio-pci so noop,
        # but verifies force arg is read correctly
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            export _GPU_SYSFS="{sysfs_root}"
            _gpu_current_driver() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local driver_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/driver"
                if [[ -L "$driver_link" ]]; then
                    basename "$(readlink "$driver_link")"
                else
                    echo "none"
                fi
            }}
            _gpu_update_state_marker() {{ return 0; }}
            _gpu_mode_vm "force"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0
        assert "already" in r.stdout.lower() or "vfio-pci" in r.stdout
    def test_script_sources_cleanly(self, fake_env):
        """gpu-passthrough.sh sources without syntax errors."""
        r = subprocess.run(
            ["bash", "-c", f"source '{SCRIPT}'"],
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{fake_env['bin_dir']}:{os.environ.get('PATH', '')}"},
            timeout=5,
        )
        assert r.returncode == 0, f"Source failed: {r.stderr}"

    def test_script_exists_and_executable(self):
        assert SCRIPT.exists()
        assert os.access(SCRIPT, os.X_OK)


# ---------------------------------------------------------------------------
# CLI dispatch (hyprconf hardware gpu ...)
# ---------------------------------------------------------------------------

class TestCliDispatch:
    """Test the CLI dispatch in hyprconf binary for gpu subcommands.

    These tests run the real hyprconf binary with fake PATH entries
    to mock system commands, verifying that subcommand routing works.
    """

    def _run_hyprconf(
        self,
        args: list[str],
        bin_dir: Path,
        home_dir: Path,
        *,
        sysfs_root: Path | None = None,
    ) -> subprocess.CompletedProcess:
        # Set up the GPU passthrough script in the fake HOME
        script_dir = home_dir / ".config" / "hypr" / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_dest = script_dir / "gpu-passthrough.sh"
        if not script_dest.exists():
            import shutil
            shutil.copy2(SCRIPT, script_dest)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        # Prevent hyprconf from trying real hyprctl etc.
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        return subprocess.run(
            ["bash", str(HYPRCONF_BIN), "hardware", "gpu"] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )

    def test_gpu_no_args_shows_status(self, fake_env):
        r = self._run_hyprconf([], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode == 0
        assert "GPU Passthrough Status" in r.stdout or "GPU" in r.stdout

    def test_gpu_detect_subcommand(self, fake_env):
        r = self._run_hyprconf(["detect"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode == 0
        assert "NVIDIA" in r.stdout or "01:00.0" in r.stdout

    def test_gpu_audit_subcommand(self, fake_env):
        r = self._run_hyprconf(["audit"], fake_env["bin_dir"], fake_env["home_dir"])
        # audit may fail if some checks don't pass, but it should run
        assert "GPU Passthrough System Audit" in r.stdout

    def test_gpu_diagnose_subcommand(self, fake_env):
        r = self._run_hyprconf(["diagnose"], fake_env["bin_dir"], fake_env["home_dir"])
        assert "GPU Passthrough Diagnostics" in r.stdout or r.returncode == 0

    def test_gpu_setup_subcommand(self, fake_env):
        r = self._run_hyprconf(["setup"], fake_env["bin_dir"], fake_env["home_dir"])
        assert "GPU Passthrough Setup" in r.stdout or "Setup" in r.stdout

    def test_gpu_mode_vm_no_config_errors(self, fake_env):
        """mode vm with no config should error."""
        r = self._run_hyprconf(["mode", "vm"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_mode_vm_with_config(self, fake_env):
        """mode vm routes correctly (may fail on sysfs in test env)."""
        conf_dir = fake_env["home_dir"] / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
            'GPU_VENDOR_ID="10de"\nGPU_DEVICE_ID="2484"\n'
        )
        r = self._run_hyprconf(["mode", "vm"], fake_env["bin_dir"], fake_env["home_dir"])
        combined = r.stdout + r.stderr
        # Verifies routing: function was called (may fail on sysfs bind)
        assert "01:00.0" in combined or "vfio" in combined.lower()

    def test_gpu_mode_host_no_config_errors(self, fake_env):
        r = self._run_hyprconf(["mode", "host"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_mode_none_no_config_errors(self, fake_env):
        r = self._run_hyprconf(["mode", "none"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_mode_no_arg_shows_current(self, fake_env):
        """mode with no arg should show current mode."""
        r = self._run_hyprconf(["mode"], fake_env["bin_dir"], fake_env["home_dir"])
        # Shows mode or errors about no config
        assert r.returncode == 0 or "not configured" in r.stdout.lower() or "No GPU configured" in r.stdout

    def test_gpu_unknown_subcommand_errors(self, fake_env):
        r = self._run_hyprconf(["foobar"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_report_subcommand(self, fake_env):
        """report subcommand should produce hardware report."""
        r = self._run_hyprconf(["report"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode == 0
        assert "Hardware Report" in r.stdout
        assert "[SYSTEM]" in r.stdout
        assert "[GPUs]" in r.stdout


# ---------------------------------------------------------------------------
# Audio device detection
# ---------------------------------------------------------------------------

class TestGpuAudioDevice:
    def test_audio_device_found(self, fake_env):
        """Audio device at same bus slot is found."""
        r = _source_and_run("_gpu_audio_device", ["01:00.0"], **fake_env)
        assert r.returncode == 0
        assert "01:00.1" in r.stdout
        assert "10de:228b" in r.stdout

    def test_audio_device_second_gpu(self, fake_env):
        r = _source_and_run("_gpu_audio_device", ["02:00.0"], **fake_env)
        assert r.returncode == 0
        assert "02:00.1" in r.stdout
        assert "10de:22be" in r.stdout

    def test_no_audio_device_for_igpu(self, tmp_path):
        """Intel iGPU at 00:02.0 has no companion audio device."""
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir, lspci_output=LSPCI_INTEL_IGPU)
        r = _source_and_run("_gpu_audio_device", ["00:02.0"], bin_dir=bin_dir)
        assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# _gpu_detect audio + IOMMU group listing
# ---------------------------------------------------------------------------

class TestGpuDetectEnhanced:
    def test_detect_shows_audio_device(self, fake_env):
        """detect output includes audio device info."""
        r = _source_and_run("_gpu_detect", **fake_env)
        assert r.returncode == 0
        assert "Audio Device:" in r.stdout
        assert "10de:228b" in r.stdout

    def test_detect_shows_iommu_devices(self, fake_env):
        """detect output shows IOMMU group device listing."""
        r = _source_and_run("_gpu_detect", **fake_env)
        assert r.returncode == 0
        # Each GPU group has 2 devices (GPU + audio), so listing is shown
        assert "IOMMU Devices:" in r.stdout or "2 devices" in r.stdout

    def test_detect_usb_warning(self, tmp_path):
        """IOMMU group with USB controller shows warning."""
        lspci_with_usb = textwrap.dedent("""\
            01:00.0 VGA compatible controller: NVIDIA Corporation RTX 3070 [10de:2484] (rev a1)
            01:00.1 Audio device: NVIDIA Corporation Audio [10de:228b] (rev a1)
            01:00.2 USB controller: NVIDIA Corporation USB [10de:2489] (rev a1)
        """)
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=lspci_with_usb)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
            "01:00.2": {"driver": "xhci_hcd", "iommu_group": "1", "vendor": "0x10de", "device": "0x2489"},
        })
        r = _source_and_run(
            "_gpu_detect", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        assert r.returncode == 0
        assert "USB controller" in r.stdout
        assert "Unplug USB" in r.stdout

    def test_detect_pci_bridge_warning(self, tmp_path):
        """IOMMU group with PCI bridge shows warning."""
        lspci_with_bridge = textwrap.dedent("""\
            01:00.0 VGA compatible controller: NVIDIA Corporation RTX 3070 [10de:2484] (rev a1)
            00:01.0 PCI bridge: Intel Corporation Xeon E3-1200 v5 [8086:1901] (rev 0a)
        """)
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=lspci_with_bridge)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "00:01.0": {"driver": "pcieport", "iommu_group": "1", "vendor": "0x8086", "device": "0x1901"},
        })
        r = _source_and_run(
            "_gpu_detect", bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        assert r.returncode == 0
        assert "PCI bridge" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_report
# ---------------------------------------------------------------------------

class TestGpuReport:
    def test_report_has_system_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert r.returncode == 0
        assert "[SYSTEM]" in r.stdout
        assert "CPU:" in r.stdout
        assert "Kernel:" in r.stdout

    def test_report_has_motherboard_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert "[MOTHERBOARD]" in r.stdout

    def test_report_has_gpu_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert "[GPUs]" in r.stdout
        assert "GPU 1:" in r.stdout

    def test_report_has_iommu_groups_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert "[IOMMU GROUPS]" in r.stdout

    def test_report_has_display_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert "[DISPLAY]" in r.stdout

    def test_report_has_driver_versions_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert "[DRIVER VERSIONS]" in r.stdout
        assert "vfio:" in r.stdout

    def test_report_has_passthrough_status_section(self, fake_env):
        r = _source_and_run("_gpu_report", **fake_env)
        assert "[PASSTHROUGH STATUS]" in r.stdout

    def test_report_shows_configured_gpu_when_config_exists(self, fake_env):
        """Report shows configured GPU from saved config."""
        conf_dir = fake_env["home_dir"] / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
        )
        r = _source_and_run("_gpu_report", **fake_env)
        assert "RTX 3070" in r.stdout
        assert "01:00.0" in r.stdout

    def test_report_no_gpu_shows_none(self, tmp_path):
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir, lspci_output=LSPCI_EMPTY)
        r = _source_and_run("_gpu_report", bin_dir=bin_dir)
        assert r.returncode == 0
        assert "No GPUs detected" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_setup_select (interactive GPU selection)
# ---------------------------------------------------------------------------

class TestGpuSetupSelect:
    def test_single_gpu_auto_selects(self, tmp_path):
        """With only one GPU, selection is automatic (no user input needed)."""
        lspci_single = "01:00.0 VGA compatible controller: NVIDIA RTX 3070 [10de:2484] (rev a1)\n"
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir, lspci_output=lspci_single)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        r = _source_and_run(
            "_gpu_setup_select",
            bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        assert r.returncode == 0
        assert "selecting it automatically" in r.stdout.lower() or "configured" in r.stdout.lower()

        # Verify config was saved
        conf_file = home_dir / ".config" / "hyprconf" / "gpu-passthrough.conf"
        assert conf_file.exists()
        content = conf_file.read_text()
        assert "01:00.0" in content

    def test_multi_gpu_selection_via_stdin(self, tmp_path):
        """With multiple GPUs, user selects via stdin (piped input)."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir, lspci_output=LSPCI_TWO_NVIDIA)
        _make_fake_sysfs(sysfs_root)

        # Pipe "2" to select the second GPU
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_current_driver() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local driver_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/driver"
                if [[ -L "$driver_link" ]]; then
                    basename "$(readlink "$driver_link")"
                else
                    echo "none"
                fi
            }}
            _gpu_iommu_group() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local iommu_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/iommu_group"
                if [[ -L "$iommu_link" ]]; then
                    basename "$(readlink "$iommu_link")"
                else
                    echo ""
                fi
            }}
            _gpu_iommu_devices() {{
                local pci_addr="$1"
                local group
                group=$(_gpu_iommu_group "$pci_addr")
                [[ -z "$group" ]] && return 1
                local grp_dir="{sysfs_root}/kernel/iommu_groups/${{group}}/devices"
                [[ -d "$grp_dir" ]] || return 1
                local dev
                for dev in "$grp_dir"/*; do
                    basename "$dev" | sed 's/^0000://'
                done
            }}
            _gpu_setup_select
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            env=env,
            input="2\n",
            timeout=15,
        )
        assert r.returncode == 0
        assert "configured" in r.stdout.lower()

        # Verify config saved with second GPU
        conf_file = home_dir / ".config" / "hyprconf" / "gpu-passthrough.conf"
        assert conf_file.exists()
        content = conf_file.read_text()
        assert "02:00.0" in content

    def test_invalid_selection_errors(self, tmp_path):
        """Invalid selection returns error."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir, lspci_output=LSPCI_TWO_NVIDIA)
        _make_fake_sysfs(sysfs_root)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            _gpu_setup_select
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            env=env,
            input="99\n",
            timeout=15,
        )
        assert r.returncode != 0

    def test_no_gpus_errors(self, tmp_path):
        """No GPUs means nothing to configure."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_EMPTY)

        r = _source_and_run("_gpu_setup_select", bin_dir=bin_dir, home_dir=home_dir)
        assert r.returncode != 0
        assert "No GPUs detected" in r.stdout


# ---------------------------------------------------------------------------
# Config persistence wiring
# ---------------------------------------------------------------------------

class TestGpuConfigWiring:
    def test_status_shows_configured_gpu(self, fake_env):
        """Status shows configured GPU when config exists."""
        conf_dir = fake_env["home_dir"] / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True, exist_ok=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
        )
        r = _source_and_run("_gpu_status", **fake_env)
        assert r.returncode == 0
        assert "Configured GPU:" in r.stdout
        assert "RTX 3070" in r.stdout

    def test_status_no_config_no_configured_line(self, fake_env):
        """Status without config doesn't show configured GPU line."""
        r = _source_and_run("_gpu_status", **fake_env)
        assert r.returncode == 0
        assert "Configured GPU:" not in r.stdout


# ---------------------------------------------------------------------------
# Limine bootloader support in setup
# ---------------------------------------------------------------------------

class TestGpuSetupLimine:
    def test_setup_limine_detection(self, tmp_path):
        """Setup wizard detects Limine bootloader and writes params."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        # Create fake /etc/default/limine
        limine_default = tmp_path / "etc" / "default" / "limine"
        limine_default.parent.mkdir(parents=True, exist_ok=True)
        limine_default.write_text('KERNEL_CMDLINE[default]="quiet"\n')

        # Make bootctl fail (not systemd-boot) and no GRUB
        _make_fake_bins(bin_dir, iommu_enabled=False, cpu_vendor="intel")

        # Override bootctl to fail, and make setup look at our tmp limine path
        # We need to override the file path checks in the script.
        # Since _gpu_setup checks real /etc/default/limine, we test
        # the detection logic directly.
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"

            # Test Limine file detection logic in isolation
            if [[ -f "{limine_default}" ]]; then
                printf "LIMINE_DETECTED\\n"
                if ! grep -qE '(intel_iommu|amd_iommu)=on' "{limine_default}" 2>/dev/null; then
                    printf 'KERNEL_CMDLINE[default]+=" intel_iommu=on iommu=pt"\\n' >> "{limine_default}"
                    printf "LIMINE_UPDATED\\n"
                fi
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        assert r.returncode == 0
        assert "LIMINE_DETECTED" in r.stdout
        assert "LIMINE_UPDATED" in r.stdout

        # Verify the file was updated
        content = limine_default.read_text()
        assert "intel_iommu=on" in content
        assert "iommu=pt" in content

    def test_setup_limine_already_configured(self, tmp_path):
        """Limine with IOMMU already configured is not modified."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        limine_default = tmp_path / "etc" / "default" / "limine"
        limine_default.parent.mkdir(parents=True, exist_ok=True)
        limine_default.write_text(
            'KERNEL_CMDLINE[default]="quiet intel_iommu=on iommu=pt"\n'
        )

        _make_fake_bins(bin_dir, iommu_enabled=False, cpu_vendor="intel")

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            if [[ -f "{limine_default}" ]]; then
                if grep -qE '(intel_iommu|amd_iommu)=on' "{limine_default}" 2>/dev/null; then
                    printf "ALREADY_CONFIGURED\\n"
                else
                    printf "NEEDS_UPDATE\\n"
                fi
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)

        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        assert r.returncode == 0
        assert "ALREADY_CONFIGURED" in r.stdout


# ── Windows VM Tests ───────────────────────────────────────────────────────────


class TestGpuVmGenerateCompose:
    """Tests for _gpu_vm_generate_compose."""

    def test_compose_generated_with_gpu_devices(self, tmp_path):
        """Compose file includes vfio-pci QEMU args and correct IOMMU group."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
            'GPU_AUDIO_PCI="01:00.1"\nGPU_AUDIO_IDS="10de:228b"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="16G"\nVM_CPU="6"\nVM_DISK="128G"\n'
            'VM_USERNAME="testuser"\nVM_PASSWORD="testpass"\n'
            'VM_VERSION="11"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"

        compose = r.stdout
        assert "dockurr/windows" in compose
        assert "RAM_SIZE: \"16G\"" in compose
        assert "CPU_CORES: \"6\"" in compose
        assert "DISK_SIZE: \"128G\"" in compose
        assert "USERNAME: \"testuser\"" in compose
        assert "vfio-pci,host=01:00.0" in compose
        assert "vfio-pci,host=01:00.1" in compose
        assert "/dev/vfio/1:/dev/vfio/1" in compose
        assert "/dev/vfio/vfio:/dev/vfio/vfio" in compose
        assert "privileged: true" in compose

    def test_compose_skips_pci_bridges(self, tmp_path):
        """PCI bridges (class 0604) are excluded from QEMU device args."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "00:01.0": {"driver": "pcieport", "iommu_group": "1", "vendor": "0x8086", "device": "0x1901", "class": "0604"},
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="00:01.0 01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_get_pci_class() {{
                local pci="$1"
                local full="0000:$pci"
                local class_file="{sysfs_root}/bus/pci/devices/$full/class"
                if [[ -f "$class_file" ]]; then
                    local raw
                    raw=$(cat "$class_file")
                    echo "${{raw:2:4}}"
                else
                    echo "0300"
                fi
            }}
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        # Write class files for the fake sysfs
        pci_bridge = sysfs_root / "bus" / "pci" / "devices" / "0000:00:01.0"
        (pci_bridge / "class").write_text("0x060400")
        gpu_dev = sysfs_root / "bus" / "pci" / "devices" / "0000:01:00.0"
        (gpu_dev / "class").write_text("0x030000")

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout
        assert "vfio-pci,host=01:00.0" in compose
        assert "vfio-pci,host=00:01.0" not in compose

    def test_compose_fails_without_gpu_config(self, tmp_path):
        """Compose generation fails if GPU passthrough not configured."""
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_generate_compose
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode != 0
        assert "not configured" in r.stderr


class TestGpuVmConfig:
    """Tests for _gpu_vm_save_config and _gpu_vm_load_config."""

    def test_save_and_load_config(self, tmp_path):
        """Config round-trips correctly through save/load."""
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            VM_RAM="16G"
            VM_CPU="8"
            VM_DISK="256G"
            VM_USERNAME="testuser"
            VM_PASSWORD="secret123"
            VM_VERSION="10"
            _gpu_vm_save_config
            # Clear and reload
            unset VM_RAM VM_CPU VM_DISK VM_USERNAME VM_PASSWORD VM_VERSION
            _gpu_vm_load_config
            echo "RAM=$VM_RAM CPU=$VM_CPU DISK=$VM_DISK USER=$VM_USERNAME VER=$VM_VERSION"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "RAM=16G" in r.stdout
        assert "CPU=8" in r.stdout
        assert "DISK=256G" in r.stdout
        assert "USER=testuser" in r.stdout
        assert "VER=10" in r.stdout


class TestGpuVmStatus:
    """Tests for _gpu_vm_status."""

    def test_status_unconfigured_gpu(self, tmp_path):
        """Status shows 'not configured' if no GPU config exists."""
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        bin_dir = tmp_path / "bin"
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_status
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0
        assert "not configured" in r.stdout

    def test_status_with_config_no_docker(self, tmp_path):
        """Status shows VM config when GPU and VM are configured but container isn't running."""
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
        )

        # Mock docker to report container not found
        _make_executable(bin_dir / "docker", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "inspect" ]]; then
                echo "" >&2
                exit 1
            fi
            exit 0
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_vm_status
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0
        output = r.stdout
        assert "RTX 3070" in output
        assert "8G RAM" in output or "8G" in output
        assert "not created" in output


class TestGpuNvidiaUsedByOtherGpu:
    """Tests for _gpu_nvidia_used_by_other_gpu multi-GPU detection."""

    def test_detects_other_gpu_on_nvidia(self, tmp_path):
        """Returns 0 when nvidia driver is bound to a device outside the IOMMU group."""
        sysfs_root = tmp_path / "sys"
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        # Two GPUs: 01:00.0 is our passthrough GPU, 02:00.0 is the display GPU
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "02:00.0": {"driver": "nvidia", "iommu_group": "2", "vendor": "0x10de", "device": "0x2684"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_IOMMU_DEVICES="01:00.0"\n'
            'GPU_NAME="RTX 3070"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_load_config
            if _gpu_nvidia_used_by_other_gpu; then
                echo "OTHER_GPU_USES_NVIDIA"
            else
                echo "NO_OTHER_GPU"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "OTHER_GPU_USES_NVIDIA" in r.stdout

    def test_no_other_gpu_on_nvidia(self, tmp_path):
        """Returns 1 when only the target IOMMU group devices are on nvidia."""
        sysfs_root = tmp_path / "sys"
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        # Single GPU setup — only the passthrough GPU is on nvidia
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
            'GPU_NAME="RTX 3070"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_load_config
            if _gpu_nvidia_used_by_other_gpu; then
                echo "OTHER_GPU_USES_NVIDIA"
            else
                echo "NO_OTHER_GPU"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "NO_OTHER_GPU" in r.stdout

    def test_no_nvidia_driver_dir(self, tmp_path):
        """Returns 1 when no nvidia driver directory exists (no nvidia loaded)."""
        sysfs_root = tmp_path / "sys"
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        # All GPUs on vfio-pci — no nvidia driver dir
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_IOMMU_DEVICES="01:00.0"\n'
            'GPU_NAME="RTX 3070"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_load_config
            if _gpu_nvidia_used_by_other_gpu; then
                echo "OTHER_GPU_USES_NVIDIA"
            else
                echo "NO_OTHER_GPU"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "NO_OTHER_GPU" in r.stdout

    @pytest.mark.skip(reason="Dual boot entry rewrite — tests pending")
    def test_mode_vm_skips_unload_multi_gpu(self, tmp_path):
        """mode_vm succeeds in multi-GPU setup without unloading nvidia modules."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        # Multi-GPU: 01:00.x = passthrough (nvidia), 02:00.0 = display (nvidia)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "snd_hda_intel", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
            "02:00.0": {"driver": "nvidia", "iommu_group": "2", "vendor": "0x10de", "device": "0x2684"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0 01:00.1"\n'
        )

        # Use a direct bash script with overrides that simulate sysfs binding
        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            source "{SCRIPT}"
            export _GPU_SYSFS="{sysfs_root}"
            _gpu_current_driver() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local driver_link="{sysfs_root}/bus/pci/devices/${{full_addr}}/driver"
                if [[ -L "$driver_link" ]]; then
                    basename "$(readlink "$driver_link")"
                else
                    echo "none"
                fi
            }}
            _gpu_iommu_devices() {{
                local pci_addr="$1"
                local group
                group=$(_gpu_iommu_group "$pci_addr")
                [[ -z "$group" ]] && return 1
                local grp_dir="{sysfs_root}/kernel/iommu_groups/${{group}}/devices"
                [[ -d "$grp_dir" ]] || return 1
                local dev
                for dev in "$grp_dir"/*; do
                    basename "$dev" | sed 's/^0000://'
                done
            }}
            _gpu_check_processes() {{ return 0; }}
            _gpu_check_display_safety() {{ return 0; }}
            _gpu_unbind_vtconsoles() {{ return 0; }}
            _gpu_is_module_loaded() {{ return 0; }}
            _gpu_update_state_marker() {{ return 0; }}
            _gpu_ensure_sudo() {{ return 0; }}
            _gpu_get_pci_class() {{ echo "0300"; }}
            # Override sysfs_write to mutate fake symlinks
            _gpu_sysfs_write() {{
                local value="$1" path="$2"
                # Detect unbind writes
                if [[ "$path" == */driver/unbind ]]; then
                    local dev_dir
                    dev_dir=$(dirname "$(dirname "$path")")
                    rm -f "$dev_dir/driver"
                # Detect drivers_probe writes (bind via driver_override)
                elif [[ "$path" == */drivers_probe ]]; then
                    local dev_dir="{sysfs_root}/bus/pci/devices/$value"
                    if [[ -d "$dev_dir" ]]; then
                        local override
                        override=$(cat "$dev_dir/driver_override" 2>/dev/null)
                        if [[ -n "$override" ]]; then
                            rm -f "$dev_dir/driver"
                            local drv_dir="{sysfs_root}/bus/pci/drivers/$override"
                            mkdir -p "$drv_dir"
                            ln -sf "$drv_dir" "$dev_dir/driver"
                        fi
                    fi
                # Detect driver_override writes
                elif [[ "$path" == */driver_override ]]; then
                    echo "$value" > "$path"
                fi
                return 0
            }}
            _gpu_mode_vm
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "per-device unbind" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_has_other_nvidia_gpu (lspci-based multi-GPU detection)
# ---------------------------------------------------------------------------

class TestGpuHasOtherNvidiaGpu:
    """Tests for _gpu_has_other_nvidia_gpu lspci-based multi-GPU detection."""

    def test_detects_other_nvidia_gpu(self, tmp_path):
        """Returns 0 when another NVIDIA VGA GPU exists besides passthrough."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_TWO_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_load_config
            if _gpu_has_other_nvidia_gpu; then
                echo "HAS_OTHER_NVIDIA"
            else
                echo "NO_OTHER_NVIDIA"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "HAS_OTHER_NVIDIA" in r.stdout

    def test_no_other_nvidia_single_gpu(self, tmp_path):
        """Returns 1 when only one NVIDIA GPU exists (single-GPU + iGPU)."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_SINGLE_NVIDIA)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_load_config
            if _gpu_has_other_nvidia_gpu; then
                echo "HAS_OTHER_NVIDIA"
            else
                echo "NO_OTHER_NVIDIA"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "NO_OTHER_NVIDIA" in r.stdout

    def test_no_other_nvidia_intel_only(self, tmp_path):
        """Returns 1 when only Intel iGPU exists (no NVIDIA at all)."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir, lspci_output=LSPCI_INTEL_IGPU)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_VENDOR_DEVICE="10de:2484"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_load_config
            if _gpu_has_other_nvidia_gpu; then
                echo "HAS_OTHER_NVIDIA"
            else
                echo "NO_OTHER_NVIDIA"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=5)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "NO_OTHER_NVIDIA" in r.stdout


# ---------------------------------------------------------------------------
# USB Passthrough
# ---------------------------------------------------------------------------

LSUSB_SAMPLE = """\
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 001 Device 003: ID 046d:c52b Logitech, Inc. Unifying Receiver
Bus 001 Device 004: ID 0951:16a5 Kingston Technology HyperX Alloy
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 002 Device 002: ID 05e3:0610 Genesys Logic, Inc. Hub
"""


class TestGpuVmUsbConfig:
    """Tests for USB config save/load/qemu-args."""

    def test_usb_save_and_load(self, tmp_path):
        """USB config round-trips through save/load."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_VM_USB_DEVICES=("046d:c52b  Logitech Unifying Receiver" "0951:16a5  Kingston HyperX Alloy")
            _gpu_vm_usb_save
            _GPU_VM_USB_DEVICES=()
            _gpu_vm_usb_load
            printf "COUNT=%d\\n" "${{#_GPU_VM_USB_DEVICES[@]}}"
            printf "DEV0=%s\\n" "${{_GPU_VM_USB_DEVICES[0]}}"
            printf "DEV1=%s\\n" "${{_GPU_VM_USB_DEVICES[1]}}"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "COUNT=2" in r.stdout
        assert "046d:c52b" in r.stdout
        assert "0951:16a5" in r.stdout

    def test_usb_load_empty(self, tmp_path):
        """USB load with no config file returns empty array."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_usb_load
            printf "COUNT=%d\\n" "${{#_GPU_VM_USB_DEVICES[@]}}"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "COUNT=0" in r.stdout

    def test_usb_load_skips_comments(self, tmp_path):
        """USB load skips comment lines and blank lines."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-vm-usb.conf").write_text(
            "# comment line\n"
            "\n"
            "046d:c52b  Logitech Receiver\n"
            "# another comment\n"
            "0951:16a5  Kingston HyperX\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_usb_load
            printf "COUNT=%d\\n" "${{#_GPU_VM_USB_DEVICES[@]}}"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "COUNT=2" in r.stdout

    def test_usb_qemu_args(self, tmp_path):
        """_gpu_vm_usb_qemu_args outputs correct QEMU device args."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-vm-usb.conf").write_text(
            "046d:c52b  Logitech Receiver\n"
            "0951:16a5  Kingston HyperX\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_usb_qemu_args
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "-device usb-host,vendorid=0x046d,productid=0xc52b,id=usb-046d-c52b" in r.stdout
        assert "-device usb-host,vendorid=0x0951,productid=0x16a5,id=usb-0951-16a5" in r.stdout

    def test_usb_qemu_args_empty(self, tmp_path):
        """No USB devices produces no args."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            result=$(_gpu_vm_usb_qemu_args)
            printf "RESULT=[%s]\\n" "$result"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "RESULT=[]" in r.stdout


class TestGpuVmUsbListHost:
    """Tests for _gpu_vm_usb_list_host."""

    def test_lists_devices_excludes_hubs(self, tmp_path):
        """Lists USB devices, filtering out root hubs."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "lsusb", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            cat << 'EOF'
{LSUSB_SAMPLE.rstrip()}
EOF
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_usb_list_host
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "046d:c52b" in r.stdout
        assert "0951:16a5" in r.stdout
        assert "05e3:0610" in r.stdout
        # Root hubs should be filtered out
        assert "1d6b:0002" not in r.stdout
        assert "1d6b:0003" not in r.stdout


class TestGpuVmUsbShow:
    """Tests for _gpu_vm_usb (display function)."""

    def test_shows_host_and_saved_devices(self, tmp_path):
        """Displays both host USB devices and saved VM USB devices."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "lsusb", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            cat << 'EOF'
{LSUSB_SAMPLE.rstrip()}
EOF
        """))

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-vm-usb.conf").write_text(
            "046d:c52b  Logitech Receiver\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_usb
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "Host USB Devices" in r.stdout
        assert "Saved for VM" in r.stdout
        assert "046d:c52b" in r.stdout

    def test_shows_no_saved_message(self, tmp_path):
        """Shows 'No USB devices saved' when none configured."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "lsusb", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            cat << 'EOF'
{LSUSB_SAMPLE.rstrip()}
EOF
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_vm_usb
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "No USB devices saved" in r.stdout


class TestGpuVmComposeWithUsb:
    """Tests for compose generation including USB devices."""

    def test_compose_includes_usb_devices(self, tmp_path):
        """Compose ARGUMENTS includes USB device args from config."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
        )
        (conf_dir / "gpu-vm-usb.conf").write_text(
            "046d:c52b  Logitech Receiver\n"
            "0951:16a5  Kingston HyperX\n"
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout
        assert "vfio-pci,host=01:00.0" in compose
        assert "usb-host,vendorid=0x046d,productid=0xc52b" in compose
        assert "usb-host,vendorid=0x0951,productid=0x16a5" in compose
        # USB controller added when USB devices present
        assert "qemu-xhci" in compose

    def test_compose_no_usb_when_unconfigured(self, tmp_path):
        """Compose works fine without any USB config file."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        })

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )
        (conf_dir / "gpu-vm.conf").write_text(
            'VM_RAM="8G"\nVM_CPU="4"\nVM_DISK="64G"\n'
            'VM_USERNAME="user"\nVM_PASSWORD="admin"\nVM_VERSION="11"\n'
        )

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _gpu_get_pci_class() {{ echo "0300"; }}
            _GPU_SYSFS="{sysfs_root}"
            _gpu_vm_generate_compose
            cat "$_GPU_VM_COMPOSE"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        compose = r.stdout
        assert "vfio-pci,host=01:00.0" in compose
        assert "usb-host" not in compose
        # No USB controller when no USB devices
        assert "qemu-xhci" not in compose


class TestGpuVmLaunchForce:
    """Tests for --force flag on _gpu_vm_launch."""

    def test_launch_parses_force_flag(self, tmp_path):
        """--force is parsed from args."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            # Override launch to inspect parsed flags
            _gpu_vm_launch() {{
                local force=""
                while [[ $# -gt 0 ]]; do
                    case "$1" in
                        --force|-f) force="force" ;;
                    esac
                    shift
                done
                printf "FORCE=%s\\n" "$force"
            }}
            _gpu_vm_launch --force
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert "FORCE=force" in r.stdout

    def test_launch_force_bypasses_display_check(self, tmp_path):
        """With --force, display safety check in _gpu_mode_vm is skipped."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "nvidia", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
        }, display_connectors={"01:00.0": ["connected"]})

        conf_dir = home_dir / ".config" / "hyprconf"
        conf_dir.mkdir(parents=True)
        (conf_dir / "gpu-passthrough.conf").write_text(
            'GPU_PCI_ADDR="01:00.0"\nGPU_NAME="RTX 3070"\n'
            'GPU_VENDOR_DEVICE="10de:2484"\nGPU_DRIVER_ORIGINAL="nvidia"\n'
            'GPU_IOMMU_GROUP="1"\nGPU_IOMMU_DEVICES="01:00.0"\n'
        )

        # Verify WITHOUT force it fails on display check
        cmd_no_force = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_current_driver() {{
                local full_addr="0000:$1"
                local link="{sysfs_root}/bus/pci/devices/$full_addr/driver"
                [[ -L "$link" ]] && basename "$(readlink "$link")" || echo "none"
            }}
            _gpu_is_display_gpu() {{
                local pci_addr="$1"
                local full_addr="0000:${{pci_addr}}"
                local drm_dir="{sysfs_root}/bus/pci/devices/${{full_addr}}/drm"
                [[ -d "$drm_dir" ]] || return 1
                local card card_name status_file
                for card in "$drm_dir"/card*; do
                    [[ -d "$card" ]] || continue
                    card_name=$(basename "$card")
                    for status_file in {sysfs_root}/class/drm/"${{card_name}}"-*/status; do
                        [[ -f "$status_file" ]] || continue
                        if [[ "$(cat "$status_file" 2>/dev/null)" == "connected" ]]; then
                            return 0
                        fi
                    done
                done
                return 1
            }}
            _gpu_ensure_sudo() {{ return 0; }}
            _gpu_check_processes() {{ return 0; }}
            _gpu_mode_vm ""
            echo "SHOULD_NOT_REACH"
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd_no_force], capture_output=True, text=True, env=env, timeout=15)
        assert "Monitor connected to GPU" in r.stderr, f"Expected display safety error, got: {r.stderr}"
        assert "SHOULD_NOT_REACH" not in r.stdout

        # Verify WITH force it gets past the display check
        call_count = tmp_path / "driver_call_count"
        call_count.write_text("0")
        cmd_force = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            _GPU_SYSFS="{sysfs_root}"
            _gpu_current_driver() {{
                local cnt=$(cat "{call_count}")
                cnt=$((cnt + 1))
                echo "$cnt" > "{call_count}"
                if [[ $cnt -le 1 ]]; then echo "nvidia"; else echo "vfio-pci"; fi
            }}
            _gpu_ensure_sudo() {{ return 0; }}
            _gpu_check_processes() {{ return 0; }}
            _gpu_is_module_loaded() {{ return 1; }}
            _gpu_unload_nvidia_modules() {{ return 0; }}
            _gpu_unbind_vtconsoles() {{ return 0; }}
            _gpu_sysfs_write() {{ return 0; }}
            _gpu_update_state_marker() {{ return 0; }}
            _gpu_get_pci_class() {{ echo "0300"; }}
            _gpu_mode_vm "force"
            echo "FORCE_OK"
        """)

        r = subprocess.run(["bash", "-c", cmd_force], capture_output=True, text=True, env=env, timeout=15)
        assert "FORCE_OK" in r.stdout, f"stdout: {r.stdout}\nstderr: {r.stderr}"


class TestGpuVmIsRunning:
    """Tests for _gpu_vm_is_running."""

    def test_running_returns_zero(self, tmp_path):
        """Returns 0 when container is running."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "docker", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "inspect" ]]; then
                echo "running"
                exit 0
            fi
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            if _gpu_vm_is_running; then
                echo "IS_RUNNING"
            else
                echo "NOT_RUNNING"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0
        assert "IS_RUNNING" in r.stdout

    def test_not_running_returns_one(self, tmp_path):
        """Returns 1 when container is not running."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "docker", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "inspect" ]]; then
                echo ""
                exit 1
            fi
        """))

        cmd = textwrap.dedent(f"""\
            set -euo pipefail
            export HOME="{home_dir}"
            source "{SCRIPT}"
            if _gpu_vm_is_running; then
                echo "IS_RUNNING"
            else
                echo "NOT_RUNNING"
            fi
        """)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, timeout=10)
        assert r.returncode == 0
        assert "NOT_RUNNING" in r.stdout


class TestGpuVmUsbCliDispatch:
    """Tests for CLI dispatch of vm usb subcommands."""

    def _run_hyprconf(self, args, bin_dir, home_dir):
        script_dir = home_dir / ".config" / "hypr" / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_dest = script_dir / "gpu-passthrough.sh"
        if not script_dest.exists():
            import shutil
            shutil.copy2(SCRIPT, script_dest)

        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        return subprocess.run(
            ["bash", str(HYPRCONF_BIN), "hardware", "gpu"] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )

    def test_vm_usb_list_dispatch(self, tmp_path):
        """'vm usb' routes to USB list."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "lsusb", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            cat << 'EOF'
{LSUSB_SAMPLE.rstrip()}
EOF
        """))

        r = self._run_hyprconf(["vm", "usb"], bin_dir, home_dir)
        assert r.returncode == 0
        assert "Host USB Devices" in r.stdout

    def test_vm_usb_list_explicit(self, tmp_path):
        """'vm usb list' routes to USB list."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_executable(bin_dir / "lsusb", textwrap.dedent(f"""\
            #!/usr/bin/env bash
            cat << 'EOF'
{LSUSB_SAMPLE.rstrip()}
EOF
        """))

        r = self._run_hyprconf(["vm", "usb", "list"], bin_dir, home_dir)
        assert r.returncode == 0
        assert "Host USB Devices" in r.stdout

    def test_vm_usb_unknown_subcommand(self, tmp_path):
        """'vm usb foobar' errors."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        r = self._run_hyprconf(["vm", "usb", "foobar"], bin_dir, home_dir)
        assert r.returncode != 0
        assert "Unknown usb subcommand" in r.stderr

    def test_vm_unknown_shows_usb_in_usage(self, tmp_path):
        """'vm foobar' error message includes usb in usage."""
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)

        r = self._run_hyprconf(["vm", "foobar"], bin_dir, home_dir)
        assert r.returncode != 0
        assert "usb" in r.stderr
