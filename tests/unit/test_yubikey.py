"""Tests for bin/hyprconf-yubikey — FIDO2 (YubiKey) unlock of the LUKS2 root.

Verifies:
- enroll: read-only preflight (Omarchy's tools, the keyboard-layout guard, the
  LUKS2-only device pick, the cmdline read) BEFORE the --yes/TTY confirmation,
  and nothing — not even omarchy-pkg-add — before it; then snapshot,
  systemd-cryptenroll with the FIDO2 flags, the mkinitcpio drop-in, the
  limine-entry-tool drop-in with the exact rd.luks.* line (Omarchy's own
  KERNEL_CMDLINE[default]+=" ..." shape, the way omarchy-hibernation-setup
  writes resume.conf), /etc/default/limine byte-identical, no .bak file, one
  limine-update rebuild, and the rebuilt image found on the ESP before success
  is announced
- every KERNEL_CMDLINE[default] shape /etc/limine-entry-tool.conf documents
  (quoted, bare with inner quotes, comment after the quotes, single quotes,
  blanks inside the quotes, pre-existing rd.luks.* of other devices) is READ
  for the mapper name and left byte-identical; the shapes refused (a line the
  tool cannot read with certainty, a plain `=` that would override the drop-in,
  a competing rd.luks.options= for the device)
- the upgrade path: hyprconf-yubikey 4.0.0–4.2.0 put the two parameters on the
  /etc/default/limine line itself — enroll and disable strip exactly those
  once (every shape), log the migration, leave the rest of the file
  byte-identical, and status says "legacy inline parameters" until then
- the mapper name comes from the read line alone (cryptdevice= cross-checked
  with root=/dev/mapper/), never from a commented or another entry's line
- limine-update's exit-0-on-failure is caught by its message and by the
  image's mtime on the ESP (UKI on UEFI per Omarchy's omarchy-uki.conf, else
  the initramfs), with an identical unrewritten image accepted only when the
  hook set did not change
- the drop-in REALLY rewrites Omarchy's exact HOOKS array when sourced by bash
- disable removes both drop-ins; remove wipes only the fido2 slot
- the verified-rebuild fingerprint: a disable after a failed enroll verifies
  against the stock image, a retried enroll still refuses a stale one; the
  cmdline drop-in is written before the hooks drop-in (the inert
  intermediate); an empty lsblk FSVER survives the field round trip; the
  UUID-less rd.luks.options global form is not "legacy"; and the interactive
  prompts (confirm, the device menu, its bounds) via _HYPRCONF_ASSUME_TTY
- status/help/sudo, and the restraint scans (no password slot, no AUR, no set
  -e, no .bak)

HERMETIC: the tool talks to sudo, lsblk, cryptsetup, systemd-cryptenroll,
limine-update, omarchy-pkg-add, omarchy-snapshot, fido2-token and
omarchy-setup-security-fido2. Every one of them is a recording stub on a
fake-bins dir put FIRST on PATH, and every system path the tool reads or
writes — /etc/default/limine and limine's other config files,
limine-entry-tool.d, mkinitcpio.conf.d, vconsole.conf, machine-id,
/usr/lib/modules, /sys/firmware/efi and the ESP itself — is pointed at a tmp
copy through its env overrides. The real ones would enrol a key into the
developer's LUKS header, rewrite their initramfs and bootloader entries, and
take a snapper snapshot. stdin is never a terminal here, so the --yes / TTY
guard is exercised on every run.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
TOOL = REPO_ROOT / "bin" / "hyprconf-yubikey"

# Every external command the tool may call; the self-check below derives the
# same set from the tool's text so a new call cannot slip past the fakes.
EXTERNALS = (
    "sudo",
    "lsblk",
    "cryptsetup",
    "systemd-cryptenroll",
    "mkinitcpio",
    "limine-update",
    "omarchy-pkg-add",
    "omarchy-snapshot",
    "fido2-token",
    "omarchy-setup-security-fido2",
)

# Omarchy 4.0.0's /etc/mkinitcpio.conf.d/omarchy_hooks.conf, verbatim; its
# omarchy_resume.conf then appends resume.
OMARCHY_HOOKS = (
    "base udev plymouth keyboard autodetect microcode modconf kms keymap "
    "consolefont block encrypt filesystems fsck btrfs-overlayfs"
)
UUID = "11111111-2222-3333-4444-555555555555"
UUID2 = "66666666-7777-8888-9999-000000000000"
DEV = "/dev/nvme0n1p2"
CMDLINE = (
    "cryptdevice=PARTUUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee:root "
    "root=/dev/mapper/root zswap.enabled=0 rootflags=subvol=@ rw rootfstype=btrfs"
)
LIMINE_LINE = f'KERNEL_CMDLINE[default]+="{CMDLINE}"'
RD_NAME = f"rd.luks.name={UUID}=root"
RD_OPTS = f"rd.luks.options={UUID}=fido2-device=auto"
ADDED = f"{RD_NAME} {RD_OPTS}"
# What hyprconf-yubikey 4.0.0–4.2.0 left in /etc/default/limine.
LEGACY_LINE = f'KERNEL_CMDLINE[default]+="{CMDLINE} {ADDED}"'
DROPIN_NAME = "zz-hyprconf-fido2.conf"
TOKEN_LINE = "/dev/hidraw3: vendor=0x1050, product=0x0407 (Yubico YubiKey OTP+FIDO+CCID)"
MACHINE_ID = "0123456789abcdef0123456789abcdef"
KERNEL_VERSION = "7.1.8-arch1-3"
# /etc/vconsole.conf as systemd-localed writes it on a stock Omarchy
VCONSOLE = "KEYMAP=us\nXKBLAYOUT=us\nXKBMODEL=pc105+inet\nXKBOPTIONS=terminate:ctrl_alt_bksp\n"
# The first-layout list Omarchy's guard withholds vconsole.conf for (omarchy_hooks.conf).
NON_LATIN = "af am ara bd bg by et ge gr il in iq ir kg kh kz la lk mk mm mn mv np rs ru sy th tj ua".split()
# What limine-mkinitcpio-install prints (error_msg) when a build fails, verbatim.
BUILD_FAILED = f"ERROR: mkinitcpio failed for kernel {KERNEL_VERSION}, skipping."

# `lsblk -rno PATH,FSTYPE,FSVER,UUID` output: raw, one space per separator,
# empty fields empty (hence the runs of spaces).
LSBLK_STOCK = (
    "/dev/nvme0n1   \n"
    "/dev/nvme0n1p1 vfat FAT32 1234-ABCD\n"
    f"{DEV} crypto_LUKS 2 {UUID}\n"
    f"/dev/mapper/root btrfs  {UUID2}\n"
)

RECORD = '#!/usr/bin/env bash\nprintf \'%s\\n\' "{name}${{*:+ $*}}" >> "$FAKE_CALLS"\n'
STUBS = {
    # execs its arguments, the way the real one would run them as root
    "sudo": 'while (($#)); do case $1 in -- | -n) shift ;; *) break ;; esac; done\nexec "$@"\n',
    "lsblk": "printf '%s\\n' \"$FAKE_LSBLK\"\nexit 0\n",
    "cryptsetup": (
        'if [[ $1 == luksDump ]]; then\n  echo "Version:        2"\n'
        "  [[ -e $FAKE_STATE/fido2-slot ]] && printf 'Tokens:\\n  0: systemd-fido2\\n'\n"
        "fi\nexit 0\n"
    ),
    "systemd-cryptenroll": (
        'case " $* " in\n  *" --wipe-slot=fido2 "*) rm -f "$FAKE_STATE/fido2-slot" ;;\n'
        '  *" --fido2-device=auto "*) touch "$FAKE_STATE/fido2-slot" ;;\nesac\nexit 0\n'
    ),
    "mkinitcpio": "exit 0\n",
    # The real one exits 0 whatever mkinitcpio did (limine-mkinitcpio-install
    # `|| true`); "ok" writes the images the test expects, "fail" prints the
    # failure message instead, "stale" builds nothing and says nothing.
    "limine-update": (
        'echo "limine-install: fake"\n'
        "case ${FAKE_LIMINE_UPDATE:-ok} in\n"
        f'  ok) echo "Building UKI for linux ({KERNEL_VERSION})"\n'
        '      while IFS= read -r f; do [[ -n $f ]] || continue; mkdir -p "${f%/*}" && : >"$f"; done'
        ' <<<"${FAKE_BOOT_IMAGES:-}" ;;\n'
        f'  fail) echo "Building UKI for linux ({KERNEL_VERSION})"; echo "{BUILD_FAILED}" >&2 ;;\n'
        "  stale) ;;\n"
        '  exit1) echo "ERROR: FAT32 boot partition not found." >&2; exit 1 ;;\n'
        "esac\nexit 0\n"
    ),
    "omarchy-pkg-add": "exit 0\n",
    "omarchy-snapshot": 'exit "${FAKE_SNAPSHOT_RC:-0}"\n',
    "fido2-token": "[[ $1 == -L && -n ${FAKE_TOKENS:-} ]] && printf '%s\\n' \"$FAKE_TOKENS\"\nexit 0\n",
    "omarchy-setup-security-fido2": 'echo "OMARCHY FIDO2 SETUP"\nexit 0\n',
}


def dropin_for(mapper: str) -> str:
    """The limine-entry-tool drop-in enroll writes, exactly — Omarchy's own
    shape (omarchy-hibernation-setup: KERNEL_CMDLINE[default]+=" resume=...")."""
    return f'KERNEL_CMDLINE[default]+=" rd.luks.name={UUID}={mapper} {RD_OPTS}"\n'


LIMINE_DROPIN = dropin_for("root")


class Box:
    """A throwaway Omarchy: fake bins, limine's config files, a mkinitcpio.conf.d,
    vconsole.conf, one installed kernel, a machine-id, a UEFI marker and an ESP.

    Stock Omarchy 4.0.0 shape: ESP_PATH in /etc/default/limine, ENABLE_UKI=yes
    from /etc/limine-entry-tool.d/omarchy-uki.conf over the packaged
    /etc/limine-entry-tool.conf's ENABLE_UKI=no, CUSTOM_UKI_NAME="omarchy" in
    omarchy-defaults.conf, resume.conf from omarchy-hibernation-setup — so the
    boot image is <ESP>/EFI/Linux/omarchy_linux.efi.
    """

    def __init__(
        self, tmp: Path, *, sd_overlay: bool = True, uki: bool = True, uefi: bool = True
    ) -> None:
        self.tmp = tmp
        self.bins = tmp / "bins"
        self.bins.mkdir()
        self.calls_file = tmp / "calls.txt"
        self.state = tmp / "state"
        self.state.mkdir()
        etc = tmp / "etc"
        self.esp = tmp / "boot"
        self.esp.mkdir()
        self.limine = etc / "default" / "limine"
        self.limine.parent.mkdir(parents=True)
        self.limine_file = f'ESP_PATH="{self.esp}"\n\n{LIMINE_LINE}\n'
        self.limine.write_text(self.limine_file)
        self.entry_conf = etc / "limine-entry-tool.conf"
        self.entry_conf.write_text("ENABLE_VERIFICATION=yes\nENABLE_UKI=no\n")
        self.conf_d = etc / "limine-entry-tool.d"
        self.conf_d.mkdir()
        (self.conf_d / "omarchy-defaults.conf").write_text(
            'TARGET_OS_NAME="Omarchy"\n\nKERNEL_CMDLINE[default]+=" quiet splash loglevel=0"\n\n'
            'KERNEL_CMDLINE[default]+=" initramfs_async=0"\n\n'
            'CUSTOM_UKI_NAME="omarchy"\nENABLE_LIMINE_FALLBACK=yes\n'
        )
        (self.conf_d / "resume.conf").write_text(
            'KERNEL_CMDLINE[default]+=" resume=/dev/mapper/root resume_offset=1234567"\n'
        )
        if uki:
            (self.conf_d / "omarchy-uki.conf").write_text("ENABLE_UKI=yes\n")
        self.omarchy_conf_d = sorted(p.name for p in self.conf_d.iterdir())
        self.usr_d = tmp / "usr" / "share" / "limine-entry-tool.d"  # absent, as on 1.37.1
        self.mkinitcpio_d = etc / "mkinitcpio.conf.d"
        self.mkinitcpio_d.mkdir()
        (self.mkinitcpio_d / "omarchy_hooks.conf").write_text(f"HOOKS=({OMARCHY_HOOKS})\n")
        (self.mkinitcpio_d / "omarchy_resume.conf").write_text("HOOKS+=(resume)\n")
        self.vconsole = etc / "vconsole.conf"
        self.vconsole.write_text(VCONSOLE)
        self.machine_id = etc / "machine-id"
        self.machine_id.write_text(f"{MACHINE_ID}\n")
        self.modules = tmp / "usr" / "lib" / "modules"
        self.add_kernel(KERNEL_VERSION, "linux")
        self.efi_dir = tmp / "sys-firmware-efi"
        if uefi:
            self.efi_dir.mkdir()
        self.initcpio_install = tmp / "initcpio-install"
        self.initcpio_install.mkdir()
        if sd_overlay:
            (self.initcpio_install / "sd-btrfs-overlayfs").write_text("#!/bin/bash\n")
        self.lsblk = LSBLK_STOCK
        self.tokens = TOKEN_LINE
        self.snapshot_rc = 0
        self.limine_update = "ok"
        self.boot_images = [self.image_path("linux", uki=uki and uefi)]
        for name, body in STUBS.items():
            fake = self.bins / name
            fake.write_text(RECORD.format(name=name) + body)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def add_kernel(self, version: str, pkgbase: str) -> None:
        d = self.modules / version
        d.mkdir(parents=True)
        (d / "pkgbase").write_text(f"{pkgbase}\n")
        (d / "vmlinuz").write_bytes(b"")

    def image_path(self, name: str, *, uki: bool = True) -> Path:
        """Where limine-mkinitcpio-install puts the image (limine-entry-tool README)."""
        if uki:
            return self.esp / "EFI" / "Linux" / f"omarchy_{name}.efi"
        return self.esp / MACHINE_ID / name / "initramfs"

    def write_stale_image(self, path: Path | None = None, *, age: int = 3600) -> Path:
        """An image from an earlier build: present, but older than any run."""
        path = path or self.boot_images[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")
        then = time.time() - age
        os.utime(path, (then, then))
        return path

    def set_limine_line(self, line: str) -> None:
        self.limine_file = f'ESP_PATH="{self.esp}"\n\n{line}\n'
        self.limine.write_text(self.limine_file)

    def make_legacy(self, line: str = LEGACY_LINE) -> None:
        """What a hyprconf-yubikey 4.0.0–4.2.0 enroll left behind: the FIDO2
        slot, the mkinitcpio drop-in, the two parameters on /etc/default/limine's
        own line — and no limine-entry-tool drop-in."""
        assert self.run("enroll", "--yes", "--device", DEV).returncode == 0
        self.limine_dropin.unlink()
        self.set_limine_line(line)
        self.reset_calls()
        assert self.enrolled and self.dropin.exists()

    @property
    def dropin(self) -> Path:
        return self.mkinitcpio_d / DROPIN_NAME

    @property
    def limine_dropin(self) -> Path:
        return self.conf_d / DROPIN_NAME

    @property
    def enrolled(self) -> bool:
        return (self.state / "fido2-slot").exists()

    def backups(self) -> list[Path]:
        return sorted(self.limine.parent.glob("limine.bak*"))

    def limine_line(self) -> str:
        return next(ln for ln in self.limine.read_text().splitlines() if ln.startswith("KERNEL_"))

    def calls(self) -> list[str]:
        return self.calls_file.read_text().splitlines() if self.calls_file.exists() else []

    def ran_as_root(self, cmd: str) -> bool:
        """Whether `cmd` went through run_root the right way for this euid:
        through the sudo stub (recorded as `sudo -- cmd`) — or, when the suite
        itself runs as root (CI does), NOT through sudo: run_root skips it
        under EUID 0, and the real command it then runs leaves no record, so
        the callers pair this with the tool's own report of the result."""
        return (f"sudo -- {cmd}" in self.calls()) is not (os.geteuid() == 0)

    def reset_calls(self) -> None:
        self.calls_file.unlink(missing_ok=True)

    def run(
        self, *args: str, stdin_text: str | None = None, assume_tty: bool = False
    ) -> subprocess.CompletedProcess:
        """assume_tty reaches the prompts through the _HYPRCONF_ASSUME_TTY
        seam; stdin_text feeds their reads (default: closed stdin, so the
        --yes/TTY refusals stay exercised on every other run)."""
        env = {
            **os.environ,
            "PATH": f"{self.bins}:{os.environ['PATH']}",
            "HOME": str(self.tmp),
            "_HYPRCONF_LIMINE_DEFAULT": str(self.limine),
            "_HYPRCONF_LIMINE_ENTRY_CONF": str(self.entry_conf),
            "_HYPRCONF_LIMINE_CONF_D": str(self.conf_d),
            "_HYPRCONF_LIMINE_USR_D": str(self.usr_d),
            "_HYPRCONF_MKINITCPIO_D": str(self.mkinitcpio_d),
            "_HYPRCONF_FIDO2_DROPIN": DROPIN_NAME,
            "_HYPRCONF_INITCPIO_INSTALL": str(self.initcpio_install),
            "_HYPRCONF_VCONSOLE": str(self.vconsole),
            "_HYPRCONF_MACHINE_ID": str(self.machine_id),
            "_HYPRCONF_MODULES_DIR": str(self.modules),
            "_HYPRCONF_EFI_DIR": str(self.efi_dir),
            "FAKE_CALLS": str(self.calls_file),
            "FAKE_STATE": str(self.state),
            "FAKE_LSBLK": self.lsblk,
            "FAKE_TOKENS": self.tokens,
            "FAKE_SNAPSHOT_RC": str(self.snapshot_rc),
            "FAKE_LIMINE_UPDATE": self.limine_update,
            "FAKE_BOOT_IMAGES": "\n".join(str(p) for p in self.boot_images),
            "_HYPRCONF_ASSUME_TTY": "1" if assume_tty else "",
        }
        stdin_opt: dict = (
            {"input": stdin_text} if stdin_text is not None else {"stdin": subprocess.DEVNULL}
        )
        return subprocess.run(
            ["bash", str(TOOL), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            **stdin_opt,
        )


@pytest.fixture
def box(tmp_path: Path) -> Box:
    return Box(tmp_path)


def _assert_untouched(box: Box, *, allow: tuple[str, ...] = ()) -> None:
    """No system change of any kind — the package install included."""
    calls = box.calls()
    for name in (
        "omarchy-pkg-add",
        "systemd-cryptenroll",
        "limine-update",
        "mkinitcpio",
        "omarchy-snapshot",
    ):
        if name in allow:
            continue
        assert not any(c.startswith(name) for c in calls), f"{name} ran: {calls}"
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []
    assert not box.enrolled


def _assert_configured(box: Box, mapper: str = "root") -> None:
    """Both drop-ins as enroll writes them, /etc/default/limine untouched."""
    assert box.dropin.is_file() and box.limine_dropin.is_file()
    assert box.limine_dropin.read_text() == dropin_for(mapper)
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []


# ---------------------------------------------------------------------------
# Hermeticity and restraint self-checks
# ---------------------------------------------------------------------------


def test_every_external_the_tool_calls_has_a_fake() -> None:
    """A new external call fails here before it can reach the real system."""
    code = "\n".join(ln for ln in TOOL.read_text().splitlines() if not ln.lstrip().startswith("#"))
    pattern = r"\b(sudo|lsblk|cryptsetup|systemd-cryptenroll|mkinitcpio|limine-update|fido2-token|omarchy-[a-z0-9-]+)\b"
    called = set(re.findall(pattern, code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= set(EXTERNALS), f"unstubbed externals: {called - set(EXTERNALS)}"


def test_restraint_scan() -> None:
    """Never the password slot, pacman, the AUR, sbctl, set -e or a .bak copy."""
    text = TOOL.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -uo pipefail" in text
    for forbidden in (
        "wipe-slot=password",
        "pacman",
        "yay",
        "makepkg",
        "omarchy-pkg-aur-add",
        "sbctl",
        "set -e",
        ".bak",
    ):
        assert forbidden not in text, f"{forbidden!r} must not appear in hyprconf-yubikey"
    assert "readonly" not in text, "system paths must stay env-overridable"
    # Root writes keep the end-of-options discipline: a value starting with
    # '-' must never become an option to a root coreutils command.
    loose = re.findall(
        r"run_root(?:_quiet)? (?:tee|rm -f|mkdir -p|chmod [0-7]+(?![0-7])|stat -c %Y)(?! --)", text
    )
    assert not loose, f"root write without -- separator: {loose}"


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------


def test_enroll_happy_path(box: Box) -> None:
    res = box.run("enroll", "--yes")  # one LUKS2 device: no --device needed
    assert res.returncode == 0, res.stderr + res.stdout
    calls = box.calls()

    # read-only preflight (lsblk) first; libfido2 only after the confirmation;
    # the snapshot BEFORE any other change
    pkg = "omarchy-pkg-add libfido2"
    assert pkg in calls and "fido2-token -L" in calls and "omarchy-snapshot create" in calls
    assert calls.index("lsblk -rno PATH,FSTYPE,FSVER,UUID") < calls.index(pkg)
    enroll = f"systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes {DEV}"
    assert enroll in calls
    assert calls.index(pkg) < calls.index("omarchy-snapshot create") < calls.index(enroll)
    assert box.enrolled

    # the rebuild is limine-update alone: it runs mkinitcpio for every kernel
    # itself (limine-mkinitcpio-install), and the mkinitcpio on Omarchy's PATH
    # is limine's interactive wrapper
    assert "limine-update" in calls
    assert calls.index(enroll) < calls.index("limine-update")
    assert not any(c.startswith("mkinitcpio") for c in calls)
    assert not any("wipe-slot" in c for c in calls)

    # the mkinitcpio drop-in, sorted after Omarchy's own, with the revert path in its header
    assert box.dropin.is_file()
    dropin = box.dropin.read_text()
    assert "hyprconf-yubikey disable" in dropin
    assert sorted(p.name for p in box.mkinitcpio_d.iterdir())[-1] == box.dropin.name

    # the cmdline goes through limine-entry-tool's drop-in dir, beside Omarchy's
    # own resume.conf — the exact one line, nothing else
    assert box.limine_dropin.read_text() == LIMINE_DROPIN
    assert box.limine_dropin.read_text() == (
        f'KERNEL_CMDLINE[default]+=" rd.luks.name={UUID}=root rd.luks.options={UUID}=fido2-device=auto"\n'
    )
    assert sorted(p.name for p in box.conf_d.iterdir()) == [*box.omarchy_conf_d, DROPIN_NAME]
    assert f"{box.limine_dropin}: written" in res.stdout

    # /etc/default/limine is read, never edited, never backed up
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []
    assert "migrated" not in res.stdout

    # the UKI limine-update wrote (Omarchy: ENABLE_UKI=yes, CUSTOM_UKI_NAME=omarchy)
    # was looked up on the ESP, as root, and found fresh — only then "Done"
    image = box.image_path("linux")
    assert image.is_file()
    assert box.ran_as_root(f"stat -c %Y -- {image}")
    assert f"{image}: rebuilt" in res.stdout
    assert "Boot images verified" in res.stdout
    assert "Done." in res.stdout and "passphrase" in res.stdout.lower()
    assert res.stdout.index("verified") < res.stdout.index("Done.")


def test_enroll_rerun_is_idempotent(box: Box) -> None:
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    dropin_first = box.dropin.read_text()
    box.reset_calls()

    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls()
    assert not any(c.startswith("systemd-cryptenroll") for c in calls), "slot already present"
    assert "limine-update" in calls
    assert f"{box.limine_dropin}: already in place" in res.stdout
    assert box.limine_dropin.read_text() == LIMINE_DROPIN
    assert box.dropin.read_text() == dropin_first
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []


def test_enroll_refuses_luks1(box: Box) -> None:
    box.lsblk = LSBLK_STOCK.replace(f"{DEV} crypto_LUKS 2 {UUID}", f"{DEV} crypto_LUKS 1 {UUID}")
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "LUKS2" in res.stderr
    _assert_untouched(box)


def test_enroll_without_token_touches_nothing(box: Box) -> None:
    """libfido2 (which fido2-token comes from) is the one install before the
    token check; everything else stays untouched."""
    box.tokens = ""
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "fido2-token" in res.stderr
    assert set(box.calls()) <= {
        "lsblk -rno PATH,FSTYPE,FSVER,UUID",
        "omarchy-pkg-add libfido2",
        "fido2-token -L",
    }
    _assert_untouched(box, allow=("omarchy-pkg-add",))


@pytest.mark.parametrize(
    ("sub", "enrolled", "before"),
    [
        ("enroll", False, ["lsblk -rno PATH,FSTYPE,FSVER,UUID"]),
        ("disable", True, []),
        ("remove", False, ["lsblk -rno PATH,FSTYPE,FSVER,UUID"]),
    ],
)
def test_refuses_without_tty_or_yes(box: Box, sub: str, enrolled: bool, before: list[str]) -> None:
    """Without a terminal and without --yes the run dies at the confirmation —
    and NOTHING ran before it but the read-only device pick, omarchy-pkg-add
    included; an enrolled box stays as it is."""
    if enrolled:
        assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
        box.reset_calls()
    res = box.run(sub, "--device", DEV)
    assert res.returncode != 0
    assert "--yes" in res.stderr
    assert box.calls() == before
    assert box.enrolled is enrolled
    assert box.dropin.exists() is enrolled and box.limine_dropin.exists() is enrolled
    if not enrolled:
        _assert_untouched(box)


def test_enroll_needs_device_flag_when_several(box: Box) -> None:
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 2 {UUID2}\n"
    res = box.run("enroll", "--yes")
    assert res.returncode != 0 and "--device" in res.stderr
    _assert_untouched(box)

    res = box.run("enroll", "--yes", "--device", "/dev/sdz")
    assert res.returncode != 0 and "/dev/sdz" in res.stderr
    _assert_untouched(box)


def test_enroll_aborts_when_snapshot_fails(box: Box) -> None:
    box.snapshot_rc = 1
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "--no-snapshot" in res.stderr
    _assert_untouched(box, allow=("omarchy-snapshot", "omarchy-pkg-add"))

    box.snapshot_rc = 127  # omarchy-snapshot: snapper not installed
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "snapper" in res.stderr and box.enrolled


# ---------------------------------------------------------------------------
# /etc/default/limine: every line shape is READ for the mapper name and left
# byte-identical; the shapes refused
# ---------------------------------------------------------------------------

CRYPT = "cryptdevice=UUID=x:root root=/dev/mapper/root rw"
READ_SHAPES = [
    pytest.param(LIMINE_LINE, "root", id="quoted-stock"),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard"',
        "root",
        id="rd.luks-of-another-uuid",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+={CRYPT} acpi_osi="Windows 2015" video=efifb:off',
        "root",
        id="bare-with-inner-quoted-parameter",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT}"   # keep me', "root", id="quoted-then-trailing-comment"
    ),
    pytest.param(f"KERNEL_CMDLINE[default]+='{CRYPT}'", "root", id="single-quoted"),
    pytest.param(
        'KERNEL_CMDLINE[default]+=" cryptdevice=UUID=x:root rw "', "root", id="blanks-inside-quotes"
    ),
    pytest.param(
        "KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw",
        "cryptroot",
        id="bare-mapper-name-from-cryptdevice",
    ),
    pytest.param(
        'KERNEL_CMDLINE[default]+="root=/dev/mapper/vault rw"',
        "vault",
        id="mapper-name-from-root-alone",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=root"',
        "root",
        id="matching-rd.luks.name-without-options-tolerated",
    ),
]


@pytest.mark.parametrize(("line", "mapper"), READ_SHAPES)
def test_cmdline_read_shapes(box: Box, line: str, mapper: str) -> None:
    box.set_limine_line(line)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    _assert_configured(box, mapper)
    assert "migrated" not in res.stdout

    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []


REFUSED_LINES = [
    pytest.param(
        'KERNEL_CMDLINE[default]+="cryptdevice=UUID=x:root root=/dev/mapper/cryptroot rw"',
        "root=/dev/mapper/cryptroot",
        id="cryptdevice-and-root-disagree",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=other"',
        f"rd.luks.name={UUID}=other",
        id="rd.luks.name-for-uuid-names-another-mapper",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.options={UUID}=discard"',
        "would override the drop-in",
        id="rd.luks.options-for-uuid-would-override-the-dropin",
    ),
    pytest.param(
        'KERNEL_CMDLINE[default]+="root=UUID=y rw"',
        "cannot tell",
        id="no-cryptdevice-no-mapper-root",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]="{CRYPT}"',
        "make it += first",
        id="plain-assignment-overrides-every-dropin",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]="quiet splash"\nKERNEL_CMDLINE[default]+="{CRYPT}"',
        "make it += first",
        id="plain-assignment-on-another-default-line",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} acpi_osi="Linux" quiet"',
        "with certainty",
        id="quoted-with-more-quotes-inside",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT}" quiet',
        "with certainty",
        id="parameters-after-the-closing-quote",
    ),
    pytest.param(
        f"KERNEL_CMDLINE[default]+={CRYPT} # comment",
        "with certainty",
        id="bare-with-hash",
    ),
    pytest.param(
        f'#KERNEL_CMDLINE[default]+="{CRYPT}"',
        "no KERNEL_CMDLINE[default] line",
        id="only-a-commented-line",
    ),
]


@pytest.mark.parametrize(("line", "reason"), REFUSED_LINES)
def test_cmdline_read_refuses_before_anything_changes(box: Box, line: str, reason: str) -> None:
    """A line the tool cannot read with certainty, or whose parameters would
    fight the drop-in, stops enroll before the confirmation: no package, slot,
    drop-in, edit."""
    box.set_limine_line(line)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert reason in res.stderr, res.stderr
    assert box.calls() == ["lsblk -rno PATH,FSTYPE,FSVER,UUID"]
    _assert_untouched(box)


def test_mapper_name_comes_from_the_read_line_only(box: Box) -> None:
    """Not from a commented line, another entry's line, or an earlier default
    line without cryptdevice= — and the whole file stays byte-identical."""
    others = (
        '#KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=old:old root=/dev/mapper/old rw"\n'
        'KERNEL_CMDLINE[linux-lts]+="cryptdevice=PARTUUID=lts:lts root=/dev/mapper/lts rw"\n'
        'KERNEL_CMDLINE[default]+=" quiet splash"\n'
    )
    mine = (
        'KERNEL_CMDLINE[default]+="cryptdevice=PARTUUID=a:cryptroot root=/dev/mapper/cryptroot rw"'
    )
    box.limine_file = f'ESP_PATH="{box.esp}"\n{others}{mine}\n'
    box.limine.write_text(box.limine_file)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    _assert_configured(box, "cryptroot")


# ---------------------------------------------------------------------------
# The upgrade path: 4.0.0–4.2.0 put the parameters on the line itself
# ---------------------------------------------------------------------------

LEGACY_SHAPES = [
    pytest.param(LEGACY_LINE, LIMINE_LINE, id="quoted-stock"),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard {ADDED}"',
        f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard"',
        id="rd.luks-of-another-uuid-survives",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+={CRYPT} acpi_osi="Windows 2015" video=efifb:off {ADDED}',
        f'KERNEL_CMDLINE[default]+={CRYPT} acpi_osi="Windows 2015" video=efifb:off',
        id="bare-with-inner-quoted-parameter",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{CRYPT} {ADDED}"   # keep me',
        f'KERNEL_CMDLINE[default]+="{CRYPT}"   # keep me',
        id="quoted-then-trailing-comment",
    ),
    pytest.param(
        f"KERNEL_CMDLINE[default]+='{CRYPT} {ADDED}'",
        f"KERNEL_CMDLINE[default]+='{CRYPT}'",
        id="single-quoted",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+=" cryptdevice=UUID=x:root rw {ADDED} "',
        'KERNEL_CMDLINE[default]+=" cryptdevice=UUID=x:root rw "',
        id="blanks-inside-quotes-kept",
    ),
    pytest.param(
        f"KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw rd.luks.name={UUID}=cryptroot {RD_OPTS}",
        "KERNEL_CMDLINE[default]+=cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw",
        id="bare-mapper-name-from-cryptdevice",
    ),
    pytest.param(
        f'KERNEL_CMDLINE[default]+="{RD_OPTS} {CRYPT} {RD_NAME}"',
        f'KERNEL_CMDLINE[default]+="{CRYPT}"',
        id="parameters-in-the-middle",
    ),
]


@pytest.mark.parametrize(("before", "after"), LEGACY_SHAPES)
def test_enroll_migrates_legacy_inline_parameters(box: Box, before: str, after: str) -> None:
    """A box a 4.0.0–4.2.0 enroll set up: the two parameters leave the line
    (nothing else on it, and no other line, changes), the drop-in takes them,
    the slot is kept — once; a re-run finds nothing to migrate."""
    box.make_legacy(before)
    mapper = "cryptroot" if "cryptroot" in before else "root"
    header = f'ESP_PATH="{box.esp}"\n\n'

    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert box.limine.read_text() == f"{header}{after}\n"
    assert box.limine_dropin.read_text() == dropin_for(mapper)
    assert box.backups() == []
    assert f"{box.limine}: migrated" in res.stdout and "4.0.0–4.2.0" in res.stdout
    assert "Migration:" in res.stdout, "announced in the plan, before the confirmation"
    assert box.ran_as_root(f"tee -- {box.limine}")
    calls = box.calls()
    assert not any(c.startswith("systemd-cryptenroll") for c in calls)
    assert "limine-update" in calls
    box.reset_calls()

    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "migrated" not in res.stdout and "Migration:" not in res.stdout
    assert box.limine.read_text() == f"{header}{after}\n"
    assert f"sudo -- tee -- {box.limine}" not in box.calls(), "no second write"

    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert box.limine.read_text() == f"{header}{after}\n"
    assert not box.dropin.exists() and not box.limine_dropin.exists()


def test_disable_migrates_legacy_inline_parameters(box: Box) -> None:
    """disable on a 4.0.0–4.2.0 box: the parameters leave the line even though
    there is no cmdline drop-in to remove; status says so before and after."""
    box.make_legacy()
    status = box.run("status").stdout
    assert "legacy inline parameters present" in status
    assert "cmdline drop-in:      absent" in status
    box.reset_calls()

    res = box.run("disable", "--yes")
    assert res.returncode == 0, res.stderr
    assert box.limine.read_text() == f'ESP_PATH="{box.esp}"\n\n{LIMINE_LINE}\n'
    assert f"{box.limine}: migrated" in res.stdout
    assert f"{box.limine_dropin}: already absent" in res.stdout
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.backups() == []
    assert "limine-update" in box.calls() and "Boot images verified" in res.stdout
    assert box.enrolled, "disable keeps the LUKS slot"
    status = box.run("status").stdout
    assert "no legacy inline parameters" in status


def test_legacy_options_beside_fido2_refuse_enroll_but_disable_strips(box: Box) -> None:
    """A user option next to the legacy fido2-device= (4.x appended to an
    existing rd.luks.options) survives the strip — and would then override
    the drop-in's, so enroll refuses; disable takes only its own back."""
    line = f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.options={UUID}=discard,fido2-device=auto {RD_NAME}"'
    box.make_legacy(line)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "would override the drop-in" in res.stderr
    assert box.limine_line() == line and box.calls() == ["lsblk -rno PATH,FSTYPE,FSVER,UUID"]

    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert box.limine_line() == f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.options={UUID}=discard"'


def test_disable_and_remove_refuse_a_legacy_line_they_cannot_read(box: Box) -> None:
    """A legacy line that cannot be read with certainty stops disable and
    remove before the confirmation: the strip must write it back."""
    box.make_legacy(LEGACY_LINE.replace(" rw ", ' acpi_osi="Linux" rw ', 1))
    corrupted = box.limine.read_text()

    res = box.run("disable", "--yes")
    assert res.returncode != 0 and "with certainty" in res.stderr
    assert box.dropin.exists() and box.calls() == []

    res = box.run("remove", "--yes", "--device", DEV)
    assert res.returncode != 0 and "with certainty" in res.stderr
    assert box.enrolled and box.dropin.exists()
    assert not any(c.startswith("systemd-cryptenroll") for c in box.calls())
    assert box.limine.read_text() == corrupted


def test_disable_does_not_need_a_readable_line_without_legacy_parameters(box: Box) -> None:
    """With nothing of its own on /etc/default/limine, disable only removes the
    drop-ins — an unreadable line there is not its business."""
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.limine.write_text(box.limine.read_text().replace(" rw ", ' acpi_osi="Linux" rw ', 1))
    corrupted = box.limine.read_text()
    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == corrupted


# ---------------------------------------------------------------------------
# The rebuild: limine-update exits 0 whatever mkinitcpio did
# ---------------------------------------------------------------------------


def test_rebuild_dies_on_limine_updates_failure_message(box: Box) -> None:
    """The exact error_msg limine-mkinitcpio-install prints, on stderr, with
    limine-update still exiting 0 — the previous image stays and still boots."""
    box.write_stale_image()
    box.limine_update = "fail"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert BUILD_FAILED in res.stderr, "limine-update's output is shown"
    assert "previous one and still boots" in res.stderr
    assert "sudo limine-update" in res.stderr
    assert "Done." not in res.stdout and "verified" not in res.stdout
    # the config changes are in place — that is what the retry rebuilds
    assert box.dropin.exists() and box.limine_dropin.read_text() == LIMINE_DROPIN


def test_rebuild_dies_on_limine_update_exit_code(box: Box) -> None:
    box.limine_update = "exit1"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "limine-update exited 1" in res.stderr and "sudo limine-update" in res.stderr
    assert "Done." not in res.stdout


def test_rebuild_dies_when_the_image_was_not_rewritten_after_a_hook_change(box: Box) -> None:
    """Exit 0, no message, but the UKI on the ESP predates the run although the
    drop-in changed the hook set: not a rebuild."""
    image = box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert f"{image} predates this run" in res.stderr
    assert "still boots" in res.stderr and "sudo limine-update" in res.stderr
    assert "Done." not in res.stdout

    # disable removes the drop-in, so the image must change again
    box.limine_update = "ok"
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode != 0 and "predates this run" in res.stderr


def test_rebuild_accepts_an_identical_unrewritten_image_when_hooks_did_not_change(
    box: Box,
) -> None:
    """mkinitcpio builds reproducibly and limine-entry-tool skips an identical
    image, so a re-run that changed nothing may find the old mtime."""
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    image = box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{image}: unchanged" in res.stdout and "Done." in res.stdout


def test_rebuild_dies_when_no_image_is_where_limine_puts_it(box: Box) -> None:
    box.boot_images = [box.esp / "somewhere" / "else.efi"]
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert f"no boot image at {box.image_path('linux')}" in res.stderr
    assert f"ESP_PATH={box.esp}" in res.stderr and "ENABLE_UKI=yes" in res.stderr


def test_rebuild_checks_every_installed_kernel(box: Box) -> None:
    box.add_kernel("6.18.9-1-lts", "linux-lts")
    leftover = box.modules / "6.0.0-old"  # modules dir without pkgbase/vmlinuz: skipped
    leftover.mkdir()
    (leftover / "extramodules").mkdir()
    lts = box.image_path("linux-lts")
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and f"no boot image at {lts}" in res.stderr

    box.boot_images.append(lts)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{lts}: rebuilt" in res.stdout and f"{box.image_path('linux')}: rebuilt" in res.stdout


@pytest.mark.parametrize(
    ("uki", "uefi"),
    [pytest.param(False, True, id="ENABLE_UKI=no"), pytest.param(True, False, id="no-UEFI")],
)
def test_rebuild_looks_for_the_initramfs_without_uki(tmp_path: Path, uki: bool, uefi: bool) -> None:
    """ENABLE_UKI=no (the packaged /etc/limine-entry-tool.conf, no omarchy-uki.conf),
    or ENABLE_UKI=yes on a non-UEFI box: <ESP>/<machine-id>/<kernel>/initramfs."""
    box = Box(tmp_path, uki=uki, uefi=uefi)
    initramfs = box.image_path("linux", uki=False)
    assert box.boot_images == [initramfs]
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{initramfs}: rebuilt" in res.stdout
    assert box.ran_as_root(f"stat -c %Y -- {initramfs}")


def test_rebuild_uki_prefix_falls_back_to_machine_id(box: Box) -> None:
    """CUSTOM_UKI_NAME must match ^[a-z0-9]+$ (limine-mkinitcpio-install
    resolve_uki_prefix), else the machine-id names the UKI."""
    defaults = box.conf_d / "omarchy-defaults.conf"
    defaults.write_text(
        defaults.read_text().replace('CUSTOM_UKI_NAME="omarchy"', 'CUSTOM_UKI_NAME="Om archy"')
    )
    image = box.esp / "EFI" / "Linux" / f"{MACHINE_ID}_linux.efi"
    box.boot_images = [image]
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert f"{image}: rebuilt" in res.stdout


def test_rebuild_without_esp_path_warns_and_relies_on_the_message(box: Box) -> None:
    box.limine_file = f"{LIMINE_LINE}\n"
    box.limine.write_text(box.limine_file)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "ESP_PATH" in res.stderr and "not double-checked" in res.stderr
    assert "Done." in res.stdout

    box.limine_update = "fail"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "still boots" in res.stderr


# ---------------------------------------------------------------------------
# The keyboard-layout guard Omarchy's omarchy_hooks.conf has and sd-vconsole lacks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", NON_LATIN)
def test_enroll_refuses_non_latin_first_layout(box: Box, layout: str) -> None:
    box.vconsole.write_text(f'KEYMAP=us\nXKBLAYOUT="{layout},us"\n')
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert layout in res.stderr and "--allow-non-latin-layout" in res.stderr
    assert box.calls() == [], "refused before the device pick, the install, anything"
    _assert_untouched(box)


def test_enroll_allow_non_latin_layout_flag_warns_and_proceeds(box: Box) -> None:
    box.vconsole.write_text("KEYMAP=ru\nXKBLAYOUT=ru\n")
    res = box.run("enroll", "--yes", "--device", DEV, "--allow-non-latin-layout")
    assert res.returncode == 0, res.stderr
    assert "warning" in res.stderr and "ru" in res.stderr and "passphrase" in res.stderr
    assert box.enrolled and box.dropin.exists()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("KEYMAP=us\nXKBLAYOUT=us,ru\n", id="latin-first"),
        pytest.param("KEYMAP=de\nXKBLAYOUT='de'\n", id="single-quoted-latin"),
        pytest.param("XKBLAYOUT=ru\nXKBLAYOUT=us\n", id="last-assignment-wins"),
        pytest.param("KEYMAP=us\n", id="no-XKBLAYOUT"),
        pytest.param(None, id="no-vconsole.conf"),
    ],
)
def test_enroll_accepts_latin_or_absent_layout(box: Box, content: str | None) -> None:
    if content is None:
        box.vconsole.unlink()
    else:
        box.vconsole.write_text(content)
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "warning" not in res.stderr


# ---------------------------------------------------------------------------
# The drop-in, sourced the way mkinitcpio sources it
# ---------------------------------------------------------------------------


def _source_dropin(box: Box, hooks: str, *, sd_overlay_dir: Path | None = None) -> list[str]:
    script = (
        "set -u\n"
        f"HOOKS=({hooks})\n"
        f'source "{box.dropin}"\n'
        "declare -p _hyprconf_hooks _hyprconf_hook >/dev/null 2>&1 && echo LEAKED\n"
        "printf '%s\\n' \"${HOOKS[@]}\"\n"
    )
    env = {
        "PATH": os.environ["PATH"],
        "_HYPRCONF_INITCPIO_INSTALL": str(sd_overlay_dir or box.initcpio_install),
    }
    res = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=30
    )
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert "LEAKED" not in lines, "the drop-in must unset its temporaries"
    return lines


def test_dropin_rewrites_omarchy_hooks(box: Box) -> None:
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0

    # Omarchy's final HOOKS: omarchy_hooks.conf + omarchy_resume.conf
    hooks = _source_dropin(box, f"{OMARCHY_HOOKS} resume")
    assert hooks == [
        "base", "systemd", "plymouth", "keyboard", "autodetect", "microcode", "modconf", "kms",
        "sd-vconsole", "block", "sd-encrypt", "filesystems", "fsck", "sd-btrfs-overlayfs",
    ]  # fmt: skip
    for gone in ("udev", "encrypt", "keymap", "consolefont", "resume", ""):
        assert gone not in hooks

    # empty elements are dropped too
    assert _source_dropin(box, 'base "" udev encrypt') == ["base", "systemd", "sd-encrypt"]

    # an already-systemd HOOKS passes through untouched (re-sourcing is a no-op)
    converted = " ".join(hooks)
    assert _source_dropin(box, converted) == hooks


def test_dropin_keeps_busybox_overlay_hook_without_sd_variant(tmp_path: Path) -> None:
    """Older limine-mkinitcpio-hook without sd-btrfs-overlayfs: keep the busybox
    hook (harmless under systemd) rather than name a hook that does not exist."""
    box = Box(tmp_path, sd_overlay=False)
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    hooks = _source_dropin(box, OMARCHY_HOOKS)
    assert hooks[-1] == "btrfs-overlayfs" and "sd-btrfs-overlayfs" not in hooks
    assert "systemd" in hooks and "sd-encrypt" in hooks


def test_shellcheck_dropin(box: Box) -> None:
    """The drop-in is generated, so this is the only shellcheck it gets (the
    tool itself is covered by `make shellcheck`)."""
    shellcheck = shutil.which("shellcheck") or pytest.skip("shellcheck is not installed")
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    res = subprocess.run(
        [shellcheck, "--severity=warning", str(box.dropin)], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# disable / remove
# ---------------------------------------------------------------------------


def test_disable_removes_both_dropins(box: Box) -> None:
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.reset_calls()

    res = box.run("disable", "--yes")
    assert res.returncode == 0, res.stderr
    calls = box.calls()
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert f"{box.limine_dropin}: removed" in res.stdout
    assert box.ran_as_root(f"rm -f -- {box.limine_dropin}")
    assert box.limine.read_text() == box.limine_file
    assert box.backups() == []
    assert "migrated" not in res.stdout
    assert "omarchy-snapshot create" in calls
    assert "limine-update" in calls
    assert "Boot images verified" in res.stdout
    assert not any(c.startswith("systemd-cryptenroll") for c in calls)
    assert box.enrolled, "disable keeps the LUKS slot"
    assert (box.mkinitcpio_d / "omarchy_hooks.conf").exists(), "Omarchy's own drop-ins stay"
    assert sorted(p.name for p in box.conf_d.iterdir()) == box.omarchy_conf_d


def test_disable_when_not_configured_changes_nothing(box: Box) -> None:
    res = box.run("disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert box.calls() == []
    assert "Nothing to rebuild" in res.stdout
    assert box.limine.read_text() == box.limine_file and box.backups() == []


def test_remove_wipes_fido2_slot_then_disables(box: Box) -> None:
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.reset_calls()

    res = box.run("remove", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls()
    wipe = f"systemd-cryptenroll --wipe-slot=fido2 {DEV}"
    assert wipe in calls
    assert calls.index(wipe) < calls.index("limine-update")
    assert not any("password" in c for c in calls), "passphrase slots are never touched"
    assert not box.enrolled
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file


# ---------------------------------------------------------------------------
# status / help / sudo
# ---------------------------------------------------------------------------


def test_status_prints_facts(box: Box) -> None:
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 1 {UUID2}\n"

    res = box.run("status")
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert f"{DEV}  LUKS2  UUID {UUID}  systemd-fido2 slot: no" in out
    assert "/dev/sdd  LUKS1" in out and "not eligible" in out
    assert f"initramfs drop-in:    absent ({box.dropin})" in out
    assert f"cmdline drop-in:      absent ({box.limine_dropin})" in out
    assert f"no legacy inline parameters ({box.limine})" in out
    assert "replaces every drop-in" not in out
    assert f"plugged in — {TOKEN_LINE}" in out
    assert "sd-btrfs-overlayfs installed" in out
    for name in ("systemd-cryptenroll", "limine-update", "omarchy-snapshot", "mkinitcpio"):
        assert not any(c.startswith(name) for c in box.calls())

    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    box.tokens = ""
    res = box.run()  # status is the default subcommand
    assert res.returncode == 0
    assert "systemd-fido2 slot: yes" in res.stdout
    assert f"initramfs drop-in:    present ({box.dropin})" in res.stdout
    assert f"cmdline drop-in:      present ({box.limine_dropin})" in res.stdout
    assert "no legacy inline parameters" in res.stdout
    assert "FIDO2 token:          none detected" in res.stdout

    box.set_limine_line(f'KERNEL_CMDLINE[default]="{CMDLINE}"')
    res = box.run("status")
    assert res.returncode == 0
    assert "KERNEL_CMDLINE[default]= (not +=)" in res.stdout and "enroll refuses it" in res.stdout


def test_status_never_fails(tmp_path: Path) -> None:
    box = Box(tmp_path, sd_overlay=False)
    box.limine.unlink()
    box.lsblk = ""
    res = box.run("status")
    assert res.returncode == 0, res.stderr
    assert "none found" in res.stdout and f"{box.limine} not found" in res.stdout
    assert "sd-btrfs-overlayfs NOT installed" in res.stdout

    box.limine.write_text('ESP_PATH="/boot"\n')
    res = box.run("status")
    assert res.returncode == 0, res.stderr
    assert "no KERNEL_CMDLINE[default] line" in res.stdout


def test_help_documents_flags_limitations_and_revert(box: Box) -> None:
    res = box.run("help")
    assert res.returncode == 0
    out = res.stdout
    for sub in ("status", "enroll", "disable", "remove", "sudo", "help"):
        assert re.search(rf"^(usage:)?\s+hyprconf-yubikey {sub}\b", out, re.M), sub
    for flag in ("--device", "--yes", "--no-snapshot", "--allow-non-latin-layout"):
        assert flag in out
    assert "snapshot" in out and "sd-btrfs-overlayfs" in out
    assert "XKBLAYOUT" in out and "omarchy_hooks.conf" in out, "the layout limitation"
    assert "mkinitcpio failed for kernel" in out and "exits 0" in out, "the rebuild check"
    assert str(box.limine_dropin) in out and "resume.conf" in out, "the cmdline seam"
    assert (
        'KERNEL_CMDLINE[default]+=" rd.luks.name=<UUID>=<name> rd.luks.options=<UUID>=fido2-device=auto"'
        in out
    )
    assert "legacy inline parameters" in out and "4.0.0–4.2.0" in out, "the upgrade path"
    assert "hyprconf-yubikey disable" in out and "hyprconf-yubikey remove" in out
    assert "Passphrase slots are never touched" in out
    assert box.run("--help").returncode == 0
    assert box.run("bogus").returncode != 0
    assert box.calls() == []


def test_sudo_subcommand_execs_omarchy_script(box: Box) -> None:
    res = box.run("sudo")
    assert res.returncode == 0, res.stderr
    assert "OMARCHY FIDO2 SETUP" in res.stdout
    assert box.calls() == ["omarchy-setup-security-fido2"]


# ---------------------------------------------------------------------------
# The audit pins: verified-rebuild fingerprints, field round-trips, write
# order, the UUID-less non-legacy shape, and the interactive paths
# ---------------------------------------------------------------------------


def test_disable_after_a_failed_enroll_rebuild_verifies_against_stock(box: Box) -> None:
    """An enroll whose rebuild failed leaves both drop-ins; disable then
    reverts them, and the pre-enroll image on the ESP — byte-identical, not
    rewritten — is the CORRECT one. A this-run changed flag called that a
    failure; the recorded-fingerprint check accepts it against stock."""
    box.limine_update = "fail"
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 1
    assert box.dropin.exists() and box.limine_dropin.exists()
    box.write_stale_image()  # the ESP still holds the pre-enroll image
    box.limine_update = "stale"  # reproducible build: identical, not rewritten
    res = box.run("disable", "--yes")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "unchanged (identical image" in res.stdout
    assert not box.dropin.exists() and not box.limine_dropin.exists()


def test_a_retried_enroll_still_refuses_a_stale_image(box: Box) -> None:
    """On the retry the drop-ins are already in place, so a this-run flag
    read 'nothing changed' and blessed the pre-enroll image silently. The
    hook set differs from the last VERIFIED rebuild: refuse."""
    box.limine_update = "fail"
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 1
    box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 1
    assert "changed since the last verified rebuild" in res.stderr


def test_enroll_rerun_on_a_box_without_the_record_accepts_and_records(box: Box) -> None:
    """A box enrolled by a release that never wrote the believed-ESP record:
    drop-ins in place, correct image, no .verified file. The documented
    idempotent re-run must accept the identical unrewritten image (and start
    the record), never die 'changed since the last verified rebuild'."""
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    state = box.mkinitcpio_d / f".{DROPIN_NAME}.verified"
    assert state.exists()
    state.unlink()  # what a prior-release enroll left behind
    box.write_stale_image()
    box.limine_update = "stale"
    res = box.run("enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "no verified-rebuild record — accepting" in res.stdout
    assert state.exists()  # recorded, so the check is armed from here on


def test_disable_removes_the_verified_record(box: Box) -> None:
    """Reverting to stock leaves no residue under /etc: both drop-ins AND
    the believed-ESP record go."""
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    state = box.mkinitcpio_d / f".{DROPIN_NAME}.verified"
    assert state.exists()
    assert box.run("disable", "--yes").returncode == 0
    assert not state.exists()


def test_empty_fsver_luks_row_reads_as_unknown_version(box: Box) -> None:
    """lsblk leaves FSVER empty when blkid cannot tell. The empty field must
    survive the awk-to-read round trip — whitespace-delimited it collapsed,
    and the UUID became the 'version' in every diagnostic."""
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS  {UUID2}\n"
    res = box.run("enroll", "--yes", "--device", "/dev/sdd")
    assert res.returncode == 1
    assert "is LUKS? — systemd-cryptenroll needs LUKS2" in res.stderr


def test_enroll_writes_the_cmdline_dropin_before_the_hooks_dropin(box: Box) -> None:
    """The inert intermediate state must come first: rd.luks.* without the
    systemd hooks is ignored by the busybox initramfs, but the hooks drop-in
    without rd.luks.* turns the next kernel upgrade's rebuild into an
    initramfs that cannot unlock the root."""
    assert box.run("enroll", "--yes", "--device", DEV).returncode == 0
    if os.geteuid() == 0:
        return  # run_root skips sudo under EUID 0 (CI): no records to order
    calls = box.calls()
    limine_i = next(i for i, c in enumerate(calls) if "tee" in c and str(box.limine_dropin) in c)
    hooks_i = next(i for i, c in enumerate(calls) if "tee" in c and str(box.dropin) in c)
    assert limine_i < hooks_i


def test_uuid_less_global_fido2_options_are_not_legacy(box: Box) -> None:
    """rd.luks.options=fido2-device=auto — systemd-cryptsetup-generator(8)'s
    global form, plausibly hand-written — is not the UUID-prefixed 4.0.0 to
    4.2.0 shape: cmdline_strip leaves it byte-identical, so calling it legacy
    made every run print 'migrated' while migrating nothing, forever."""
    line = f'KERNEL_CMDLINE[default]+="{CMDLINE} rd.luks.options=fido2-device=auto"'
    box.set_limine_line(line)
    res = box.run("status")
    assert "no legacy inline parameters" in res.stdout
    res = box.run("disable", "--yes")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "migrated" not in res.stdout
    assert box.limine.read_text() == box.limine_file


def test_interactive_confirm_n_aborts_untouched(box: Box) -> None:
    res = box.run("enroll", "--device", DEV, assume_tty=True, stdin_text="n\n")
    assert res.returncode == 1
    assert "aborted — nothing changed" in res.stderr
    assert not box.dropin.exists() and not box.limine_dropin.exists()


def test_interactive_menu_picks_the_numbered_device(box: Box) -> None:
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 2 {UUID2}\n"
    res = box.run("enroll", assume_tty=True, stdin_text="2\ny\n")
    assert res.returncode == 0, res.stdout + res.stderr
    assert UUID2 in box.limine_dropin.read_text()


def test_interactive_menu_rejects_an_out_of_range_choice(box: Box) -> None:
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 2 {UUID2}\n"
    res = box.run("enroll", assume_tty=True, stdin_text="9\n")
    assert res.returncode == 1 and "invalid choice" in res.stderr
    assert not box.dropin.exists()
