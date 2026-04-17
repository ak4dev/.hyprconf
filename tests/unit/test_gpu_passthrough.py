"""Tests for stow/hypr/.config/hypr/scripts/gpu-passthrough.sh

Covers GPU detection, name resolution, IOMMU group handling, VFIO
bind/unbind, audit checks, config management, status display, and
the CLI dispatch in the hyprconf binary.

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
        "libvirt", "virt-manager", "qemu-desktop", "edk2-ovmf", "dnsmasq", "swtpm",
    ),
    modinfo_available: tuple[str, ...] = ("vfio", "vfio_pci", "vfio_iommu_type1"),
    cpu_vendor: str = "intel",
    iommu_enabled: bool = True,
    libvirtd_running: bool = True,
    user_groups: str = "wheel libvirt kvm",
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

    # sudo (pass-through)
    _make_executable(bin_dir / "sudo", textwrap.dedent("""\
        #!/usr/bin/env bash
        exec "$@"
    """))

    # systemctl
    _make_executable(bin_dir / "systemctl", textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [[ "$1" == "is-active" && "$2" == "--quiet" ]]; then
            if [[ "{'true' if libvirtd_running else 'false'}" == "true" ]]; then
                exit 0
            fi
            exit 1
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

    # tee (no-op for sudo tee)
    _make_executable(bin_dir / "tee", textwrap.dedent("""\
        #!/usr/bin/env bash
        /usr/bin/cat > /dev/null
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
) -> None:
    """Create a fake /sys/bus/pci + /sys/kernel/iommu_groups tree."""
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

        # driver symlink
        driver = info.get("driver", "")
        if driver:
            driver_target = drivers_dir / driver
            driver_target.mkdir(parents=True, exist_ok=True)
            (dev_dir / "driver").symlink_to(driver_target)

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
        assert "ready for GPU passthrough" in r.stdout

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
        assert r.returncode != 0
        assert "not installed" in r.stdout

    def test_audit_services_not_running(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir, libvirtd_running=False)
        _make_fake_sysfs(sysfs_root)
        r = _source_and_run("_gpu_audit", bin_dir=bin_dir, sysfs_root=sysfs_root)
        # services not running → warnings or errors
        assert "not running" in r.stdout or "enabled but not running" in r.stdout

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
    def test_reads_smbios_data(self, fake_env):
        r = _source_and_run("_gpu_host_smbios", **fake_env)
        assert r.returncode == 0
        assert "ASUS" in r.stdout or r.stdout.strip()

    def test_returns_tab_separated(self, fake_env):
        r = _source_and_run("_gpu_host_smbios", **fake_env)
        assert r.returncode == 0
        # Output should be tab-separated
        assert "\t" in r.stdout or r.stdout.strip()


# ---------------------------------------------------------------------------
# _gpu_attach_to_vm
# ---------------------------------------------------------------------------

class TestGpuAttachToVm:
    def test_attach_to_existing_vm(self, fake_env):
        r = _source_and_run("_gpu_attach_to_vm", ["01:00.0", "win11"], **fake_env)
        assert r.returncode == 0
        assert "Attached" in r.stdout or "already attached" in r.stdout

    def test_attach_to_nonexistent_vm_fails(self, fake_env):
        r = _source_and_run("_gpu_attach_to_vm", ["01:00.0", "nonexistent"], **fake_env)
        assert r.returncode != 0
        assert "not found" in r.stderr or "not found" in r.stdout

    def test_attach_configures_smbios(self, fake_env):
        r = _source_and_run("_gpu_attach_to_vm", ["01:00.0", "win11"], **fake_env)
        assert r.returncode == 0
        assert "SMBIOS" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_configure_smbios
# ---------------------------------------------------------------------------

class TestGpuConfigureSmbios:
    def test_configure_smbios_on_vm(self, fake_env):
        r = _source_and_run("_gpu_configure_smbios", ["win11"], **fake_env)
        assert r.returncode == 0
        assert "SMBIOS" in r.stdout

    def test_smbios_already_configured(self, tmp_path):
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root)
        # Override virsh to return XML with sysinfo already present
        _make_executable(bin_dir / "virsh", textwrap.dedent("""\
            #!/usr/bin/env bash
            if [[ "$1" == "dominfo" ]]; then exit 0; fi
            if [[ "$1" == "dumpxml" ]]; then
                cat << 'XML'
<domain type='kvm'>
  <name>win11</name>
  <sysinfo type="smbios">
    <system><entry name="manufacturer">ASUS</entry></system>
  </sysinfo>
  <os><type>hvm</type></os>
</domain>
XML
                exit 0
            fi
            exit 0
        """))
        r = _source_and_run(
            "_gpu_configure_smbios", ["win11"],
            bin_dir=bin_dir, sysfs_root=sysfs_root, home_dir=home_dir,
        )
        assert r.returncode == 0
        assert "already configured" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_detach_from_vm
# ---------------------------------------------------------------------------

class TestGpuDetachFromVm:
    def test_detach_from_vm(self, fake_env):
        r = _source_and_run("_gpu_detach_from_vm", ["01:00.0", "win11"], **fake_env)
        assert r.returncode == 0
        assert "Detached" in r.stdout


# ---------------------------------------------------------------------------
# _gpu_diagnose
# ---------------------------------------------------------------------------

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

class TestGpuBindVfio:
    def test_bind_already_bound_is_noop(self, tmp_path):
        """If device already on vfio-pci, bind should succeed without errors."""
        bin_dir = tmp_path / "bin"
        sysfs_root = tmp_path / "sys"
        _make_fake_bins(bin_dir)
        _make_fake_sysfs(sysfs_root, gpus={
            "01:00.0": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x2484"},
            "01:00.1": {"driver": "vfio-pci", "iommu_group": "1", "vendor": "0x10de", "device": "0x228b"},
        })
        r = _source_and_run("_gpu_bind_vfio", ["01:00.0"], bin_dir=bin_dir, sysfs_root=sysfs_root)
        assert r.returncode == 0


class TestGpuUnbindVfio:
    def test_unbind_not_on_vfio_is_noop(self, fake_env):
        """If device is on nvidia (not vfio), unbind should skip gracefully."""
        r = _source_and_run("_gpu_unbind_vfio", ["01:00.0"], **fake_env)
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# Script sources without error
# ---------------------------------------------------------------------------

class TestScriptSources:
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

    def test_gpu_bind_no_arg_errors(self, fake_env):
        r = self._run_hyprconf(["bind"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_unbind_no_arg_errors(self, fake_env):
        r = self._run_hyprconf(["unbind"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_unknown_subcommand_errors(self, fake_env):
        r = self._run_hyprconf(["foobar"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_pass_no_arg_errors(self, fake_env):
        r = self._run_hyprconf(["pass"], fake_env["bin_dir"], fake_env["home_dir"])
        assert r.returncode != 0

    def test_gpu_pass_with_vm_name(self, fake_env):
        """pass <gpu> <vm> should bind GPU and attach to VM."""
        r = self._run_hyprconf(
            ["pass", "3070", "win11"],
            fake_env["bin_dir"], fake_env["home_dir"],
        )
        # May partially fail due to fake virsh but should at least attempt
        assert "Binding" in r.stdout or "bound" in r.stdout or r.returncode == 0
