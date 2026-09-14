"""modules/yubikey — the install link, and bin/hyprconf-yubikey itself.

The tool enrols a key into the LUKS header, rewrites the initramfs hook set and
the kernel cmdline, and rebuilds the boot images — so the real sudo,
systemd-cryptenroll, limine-mkinitcpio and omarchy-snapshot would do all of that
to the developer's own machine, and findmnt/lsblk would answer for it. Every
external is therefore a recording stub first on PATH (the `box` fixture in the
root conftest.py, with the bodies below over it) and every system path an env
seam pointed at a tmp copy. stdin is never a terminal here, so the --yes / TTY
guard is exercised on every run that does not ask for one.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
INSTALL = MODULE / "install"
TOOL = MODULE / "bin" / "hyprconf-yubikey"

# Omarchy 4.0.0's /etc/mkinitcpio.conf.d/omarchy_hooks.conf, verbatim; its
# omarchy_resume.conf then appends resume. Unchanged in 4.0.3-1.
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
RD_OPTS = f"rd.luks.options={UUID}=fido2-device=auto"
DROPIN_NAME = "zz-hyprconf-fido2.conf"
TOKEN_LINE = "/dev/hidraw3: vendor=0x1050, product=0x0407 (Yubico YubiKey OTP+FIDO+CCID)"
KERNEL_VERSION = "7.1.8-arch1-3"
# /etc/vconsole.conf as systemd-localed writes it on a stock Omarchy
VCONSOLE = "KEYMAP=us\nXKBLAYOUT=us\nXKBMODEL=pc105+inet\nXKBOPTIONS=terminate:ctrl_alt_bksp\n"
# The first-layout list Omarchy's guard withholds vconsole.conf for
# (/etc/mkinitcpio.conf.d/omarchy_hooks.conf; Omarchy's own second copy of it is
# default/hypr/input.lua:24-27). Neither is under $OMARCHY_PATH in a shape a suite that
# must pass without Omarchy could read, so it is copied here and pinned against the
# tool's case line below.
NON_LATIN = "af am ara bd bg by et ge gr il in iq ir kg kh kz la lk mk mm mn mv np rs ru sy th tj ua".split()
# What limine-mkinitcpio-install prints (error_msg) when a build fails, verbatim.
BUILD_FAILED = f"ERROR: mkinitcpio failed for kernel {KERNEL_VERSION}, skipping."
# The real /usr/lib/initcpio/install, hardcoded in the shipped drop-in (it is sourced by
# root at every rebuild, so it carries no test seam); _source_dropin swaps it out.
INITCPIO_INSTALL = "/usr/lib/initcpio/install"

# `lsblk -rno PATH,FSTYPE,FSVER,UUID` output: raw, one space per separator, empty fields
# empty (hence the runs of spaces).
LSBLK_STOCK = (
    "/dev/nvme0n1   \n"
    "/dev/nvme0n1p1 vfat FAT32 1234-ABCD\n"
    f"{DEV} crypto_LUKS 2 {UUID}\n"
    f"/dev/mapper/root btrfs  {UUID2}\n"
)

# The bodies this tool's externals need over the box's recording stubs; limine-update is
# deliberately absent — the rebuild is limine-mkinitcpio, the tool Omarchy runs after
# its own drop-in changes (omarchy-hibernation-setup says why limine-update is the wrong
# one here: it would re-deploy the bootloader binary and build a second time), so a call
# to it finds no fake and test_every_external_the_tool_calls_has_a_fake turns red.
STUBS = {
    # execs its arguments, the way the real one would run them as root
    "sudo": 'while (($#)); do case $1 in -- | -n) shift ;; *) break ;; esac; done\nexec "$@"\n',
    # two shapes: the LUKS listing, and the picked device's own tree (NAME,TYPE), which
    # is where the `crypt` child the device is open under shows up
    "lsblk": (
        'case " $* " in\n'
        '  *" NAME,TYPE "*) printf \'%s\\n\' "$FAKE_LSBLK_CRYPT" ;;\n'
        "  *) printf '%s\\n' \"$FAKE_LSBLK\" ;;\n"
        "esac\nexit 0\n"
    ),
    "findmnt": "printf '%s\\n' \"$FAKE_ROOT_SOURCE\"\nexit 0\n",
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
    # The real one is `echo rebuild | limine-mkinitcpio-install` and exits 0 whatever
    # mkinitcpio did (`|| true` there): "ok" says so, "fail" prints the failure message
    # instead, "exit1" is the one case that does exit non-zero.
    "limine-mkinitcpio": (
        "case ${FAKE_LIMINE_MKINITCPIO:-ok} in\n"
        f'  ok) echo "Building UKI for linux ({KERNEL_VERSION})" ;;\n'
        f'  fail) echo "Building UKI for linux ({KERNEL_VERSION})"; echo "{BUILD_FAILED}" >&2 ;;\n'
        '  exit1) echo "ERROR: FAT32 boot partition not found." >&2; exit 1 ;;\n'
        "esac\nexit 0\n"
    ),
    # `limine-entry-tool --get-cmdline <kernel name>` (its --help): the
    # KERNEL_CMDLINE[default] limine's loader assembles out of its four config layers.
    # Built here from the box's own files — /etc/default/limine's parameters first and
    # the drop-ins' after them, the order the real tool prints on a live box, which is
    # why a per-file read cannot say which layer wins. A plain `=` in /etc/default/limine
    # replaces every drop-in's parameters (/etc/limine-entry-tool.conf:38-43), so the
    # stub models that too. FAKE_BASE_CMDLINE replaces the /etc/default/limine layer
    # (the drop-ins still land on top of it); FAKE_CMDLINE_FROZEN and
    # FAKE_CMDLINE_SILENT replace the whole answer, and nothing written can move it.
    "limine-entry-tool": (
        "[[ ${1:-} == --get-cmdline ]] || exit 2\n"
        "[[ -n ${FAKE_CMDLINE_SILENT:-} ]] && exit 0\n"
        "if [[ -n ${FAKE_CMDLINE_FROZEN-} ]]; then printf '%s\\n' \"$FAKE_CMDLINE_FROZEN\"; exit 0; fi\n"
        'out="" plain=""\n'
        'files=("$_HYPRCONF_LIMINE_DEFAULT" "$_HYPRCONF_LIMINE_CONF_D"/*.conf)\n'
        "if [[ -n ${FAKE_BASE_CMDLINE-} ]]; then\n"
        '  out=" $FAKE_BASE_CMDLINE"; files=("$_HYPRCONF_LIMINE_CONF_D"/*.conf)\n'
        "fi\n"
        'for f in "${files[@]}"; do\n'
        "  [[ -f $f ]] || continue\n"
        "  while IFS= read -r v; do\n"
        "    case $v in\n"
        '      +=*) out+=" ${v#+=}" ;;\n'
        "      =*) plain=${v#=} ;;\n"
        "    esac\n"
        "  done \\\n"
        '    < <(sed -n \'s/^[[:space:]]*KERNEL_CMDLINE\\[default\\]\\([+]\\?=\\)/\\1/p\' "$f" | tr -d "\\"\'")\n'
        "done\n"
        "printf '%s\\n' \"${plain:-${out# }}\"\nexit 0\n"
    ),
    "omarchy-pkg-add": "exit 0\n",
    "omarchy-snapshot": 'exit "${FAKE_SNAPSHOT_RC:-0}"\n',
    "fido2-token": "[[ $1 == -L && -n ${FAKE_TOKENS:-} ]] && printf '%s\\n' \"$FAKE_TOKENS\"\nexit 0\n",
    "omarchy-setup-security-fido2": 'echo "OMARCHY FIDO2 SETUP"\nexit 0\n',
}


def dropin_for(mapper: str) -> str:
    """The limine-entry-tool drop-in enroll writes, exactly — Omarchy's own shape
    (omarchy-hibernation-setup:138: KERNEL_CMDLINE[default]+=" resume=...")."""
    return f'KERNEL_CMDLINE[default]+=" rd.luks.name={UUID}={mapper} {RD_OPTS}"\n'


LIMINE_DROPIN = dropin_for("root")


@pytest.fixture
def box(box: Box) -> Box:
    """The box fixture (conftest.py) made into a throwaway Omarchy: limine's config
    files, a mkinitcpio.conf.d, vconsole.conf, each behind the tool's own _HYPRCONF_*
    seam, and this tool's externals given bodies over the box's recording stubs.

    Stock Omarchy 4.0.0 shape, unchanged in 4.0.3-1: ESP_PATH and the cryptdevice line
    in /etc/default/limine, the parameter drop-ins in /etc/limine-entry-tool.d/ beside
    Omarchy's own resume.conf, and one LUKS2 device open as /dev/mapper/root.

    The paths and the fakes' knobs hang on the box as plain attributes; the knobs are
    read at run() time, so a test can set them after setup.
    """
    box.state = box.tmp / "state"
    box.state.mkdir()
    box.limine = box.etc / "default" / "limine"
    box.limine.parent.mkdir(parents=True)
    box.limine_file = f'ESP_PATH="/boot"\n\n{LIMINE_LINE}\n'
    box.limine.write_text(box.limine_file)
    box.conf_d = box.etc / "limine-entry-tool.d"
    box.conf_d.mkdir()
    (box.conf_d / "omarchy-defaults.conf").write_text(
        'TARGET_OS_NAME="Omarchy"\n\nKERNEL_CMDLINE[default]+=" quiet splash loglevel=0"\n\n'
        'KERNEL_CMDLINE[default]+=" initramfs_async=0"\n\n'
        'CUSTOM_UKI_NAME="omarchy"\nENABLE_LIMINE_FALLBACK=yes\n'
    )
    (box.conf_d / "resume.conf").write_text(
        'KERNEL_CMDLINE[default]+=" resume=/dev/mapper/root resume_offset=1234567"\n'
    )
    box.omarchy_conf_d = sorted(p.name for p in box.conf_d.iterdir())
    box.mkinitcpio_d = box.etc / "mkinitcpio.conf.d"
    box.mkinitcpio_d.mkdir()
    (box.mkinitcpio_d / "omarchy_hooks.conf").write_text(f"HOOKS=({OMARCHY_HOOKS})\n")
    (box.mkinitcpio_d / "omarchy_resume.conf").write_text("HOOKS+=(resume)\n")
    box.dropin = box.mkinitcpio_d / DROPIN_NAME
    box.limine_dropin = box.conf_d / DROPIN_NAME
    box.vconsole = box.etc / "vconsole.conf"
    box.vconsole.write_text(VCONSOLE)
    box.initcpio_install = box.tmp / "initcpio-install"
    box.initcpio_install.mkdir()
    (box.initcpio_install / "sd-btrfs-overlayfs").write_text("#!/bin/bash\n")
    box.lsblk = LSBLK_STOCK
    box.crypt_child = "root"  # `lsblk -rno NAME,TYPE <dev>`: what DEV is open as
    box.root_source = "/dev/mapper/root"  # `findmnt -no SOURCE --nofsroot /`
    box.tokens = TOKEN_LINE
    box.snapshot_rc = 0
    box.limine_mkinitcpio = "ok"
    box.base_cmdline = ""  # empty: the stub assembles it from the box's own files
    box.frozen_cmdline = ""  # non-empty: limine's answer never moves, whatever is written
    box.cmdline_silent = ""  # non-empty: limine-entry-tool prints nothing at all
    box.env.update(
        {
            "_HYPRCONF_LIMINE_DEFAULT": str(box.limine),
            "_HYPRCONF_LIMINE_CONF_D": str(box.conf_d),
            "_HYPRCONF_MKINITCPIO_D": str(box.mkinitcpio_d),
            "_HYPRCONF_INITCPIO_INSTALL": str(box.initcpio_install),
            "_HYPRCONF_VCONSOLE": str(box.vconsole),
            "FAKE_STATE": str(box.state),
        }
    )
    for name, body in STUBS.items():
        box.stub(name, body)
    return box


def run(
    box: Box, *args: str, stdin_text: str | None = None, assume_tty: bool = False
) -> subprocess.CompletedProcess:
    """The tool against the box. The fakes' knobs are read here, so a test may set them
    at any point before the run; assume_tty reaches the prompt through the
    _HYPRCONF_ASSUME_TTY seam and stdin_text feeds its read."""
    box.env.update(
        FAKE_LSBLK=box.lsblk,
        FAKE_LSBLK_CRYPT=f"nvme0n1p2 part\n{box.crypt_child} crypt" if box.crypt_child else "",
        FAKE_ROOT_SOURCE=box.root_source,
        FAKE_TOKENS=box.tokens,
        FAKE_SNAPSHOT_RC=str(box.snapshot_rc),
        FAKE_LIMINE_MKINITCPIO=box.limine_mkinitcpio,
        FAKE_BASE_CMDLINE=box.base_cmdline,
        FAKE_CMDLINE_FROZEN=box.frozen_cmdline,
        FAKE_CMDLINE_SILENT=box.cmdline_silent,
    )
    return box.run(TOOL, *args, tty=assume_tty, stdin=stdin_text)


def set_limine_line(box: Box, line: str) -> None:
    box.limine_file = f'ESP_PATH="/boot"\n\n{line}\n'
    box.limine.write_text(box.limine_file)


def set_mapper(box: Box, mapper: str) -> None:
    """The running system agrees with the cmdline: the picked device is open under
    <mapper> and the live root is /dev/mapper/<mapper>."""
    box.crypt_child = mapper
    box.root_source = f"/dev/mapper/{mapper}"


def drop_sd_overlay(box: Box) -> None:
    """An older limine-mkinitcpio-hook, without the sd-btrfs-overlayfs hook."""
    (box.initcpio_install / "sd-btrfs-overlayfs").unlink()


def has_fido2_slot(box: Box) -> bool:
    return (box.state / "fido2-slot").exists()


def ran_as_root(box: Box, cmd: str) -> bool:
    """Whether `cmd` went through run_root — the sudo stub records it as `sudo -- cmd`."""
    return f"sudo -- {cmd}" in box.calls


def unpadded(text: str) -> str:
    """Status pads its labels into columns: match on what it says and the path it names,
    not on the width of the gap."""
    return re.sub(r"[ \t]{2,}", " ", text)


def home_state(box: Box) -> dict:
    """Every path under $HOME with the facts a rewrite would change — mode, inode,
    mtime and, for a link, its target. Equal across two runs == "wrote nothing"."""
    out = {}
    for p in sorted(box.home.rglob("*")):
        st = p.lstat()
        target = os.readlink(p) if p.is_symlink() else None
        out[str(p.relative_to(box.home))] = (st.st_mode, st.st_ino, st.st_mtime_ns, target)
    return out


def _assert_untouched(box: Box, *, allow: tuple[str, ...] = ()) -> None:
    """No system change of any kind — the package install included."""
    calls = box.calls
    for name in (
        "omarchy-pkg-add",
        "systemd-cryptenroll",
        "limine-mkinitcpio",
        "mkinitcpio",
        "omarchy-snapshot",
    ):
        if name in allow:
            continue
        assert not any(c.startswith(name) for c in calls), f"{name} ran: {calls}"
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file
    assert not has_fido2_slot(box)


def _assert_configured(box: Box, mapper: str = "root") -> None:
    """Both drop-ins as enroll writes them, /etc/default/limine untouched."""
    assert box.dropin.is_file() and box.limine_dropin.is_file()
    assert box.limine_dropin.read_text() == dropin_for(mapper)
    assert box.limine.read_text() == box.limine_file


# ---------------------------------------------------------------------------
# The module: one symlink into ~/.local/bin, and its undo
# ---------------------------------------------------------------------------


def test_install_links_the_tool_and_a_second_run_writes_nothing(box: Box) -> None:
    """~/.local/bin is on the session PATH (default/bash/env-bootstrap:38-39), so the
    link is the whole install. The second run must not even re-create it: `ln -sfn`
    would hand the link a new inode."""
    res = box.run(INSTALL)
    assert res.returncode == 0, res.stderr
    link = box.home / ".local" / "bin" / "hyprconf-yubikey"
    assert link.is_symlink() and os.readlink(link) == str(TOOL)
    assert box.calls == [], "installing runs no command at all"
    before = home_state(box)

    res = box.run(INSTALL)
    assert res.returncode == 0, res.stderr
    assert home_state(box) == before
    assert box.calls == []


@pytest.mark.parametrize("kind", ["stale-link", "pre-module-copy"])
def test_install_replaces_what_is_there_and_leaves_the_rest_of_local_bin_alone(
    box: Box, kind: str
) -> None:
    """A link to somewhere else, or the plain copy every release up to the module split
    installed — both become the link, and nothing else in ~/.local/bin is touched."""
    bin_dir = box.home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    if kind == "stale-link":
        (bin_dir / "hyprconf-yubikey").symlink_to("/nowhere/hyprconf-yubikey")
    else:
        (bin_dir / "hyprconf-yubikey").write_text("#!/usr/bin/env bash\n# an older copy\n")
    (bin_dir / "something-else").write_text("#!/bin/sh\n")
    assert box.run(INSTALL).returncode == 0
    assert os.readlink(bin_dir / "hyprconf-yubikey") == str(TOOL)
    assert (bin_dir / "something-else").read_text() == "#!/bin/sh\n"


def test_undo_removes_the_link_only_and_is_idempotent(box: Box) -> None:
    """Undo takes the tool off PATH; it reverts no boot config — that is
    `hyprconf-yubikey remove`, which needs the tool, so undo says so."""
    assert box.run(INSTALL).returncode == 0
    bin_dir = box.home / ".local" / "bin"
    (bin_dir / "something-else").write_text("#!/bin/sh\n")

    res = box.undo("yubikey")
    assert res.returncode == 0, res.stderr
    assert not (bin_dir / "hyprconf-yubikey").exists()
    assert (bin_dir / "something-else").exists()
    assert "remove" in res.stdout
    assert box.calls == []

    res = box.undo("yubikey")  # nothing to do
    assert res.returncode == 0 and box.calls == []


# ---------------------------------------------------------------------------
# Hermeticity and restraint self-checks
# ---------------------------------------------------------------------------


def test_every_external_the_tool_calls_has_a_fake(box: Box) -> None:
    """A new external call fails here before it can reach the real system.
    limine-update is scanned for and has no fake on purpose: the rebuild is
    limine-mkinitcpio, the tool Omarchy runs after its own drop-in changes
    (omarchy-hibernation-setup says why limine-update is the wrong one here — it would
    re-deploy the bootloader binary and build a second time), so a call to it is drift,
    and turns this red."""
    code = "\n".join(ln for ln in TOOL.read_text().splitlines() if not ln.lstrip().startswith("#"))
    pattern = (
        r"\b(sudo|lsblk|findmnt|cryptsetup|systemd-cryptenroll|mkinitcpio|limine-mkinitcpio"
        r"|limine-update|limine-entry-tool"
        r"|fido2-token|omarchy-[a-z0-9-]+)\b"
    )
    called = set(re.findall(pattern, code))
    assert called, "no external calls found — the scan regex is broken"
    assert called <= box.fakes, f"unstubbed externals: {sorted(called - box.fakes)}"


def test_restraint_scan() -> None:
    """This tool's own invariants: never the password slot, never sbctl (it signs
    nothing), never errexit (it handles its own failures) and never a backup copy of a
    system file. The shebang, the `set -` line and the overridable seams are the shared
    script scan's, the pacman and AUR forms the shared package scan's."""
    text = TOOL.read_text()
    for forbidden in ("wipe-slot=password", "sbctl", "set -e", ".bak"):
        assert forbidden not in text, f"{forbidden!r} must not appear in hyprconf-yubikey"
    # Root writes keep the end-of-options discipline: a value starting with '-' must
    # never become an option to a root coreutils command.
    loose = re.findall(r"run_root(?:_quiet)? (?:tee|rm -f|mkdir -p)(?! --)", text)
    assert not loose, f"root write without -- separator: {loose}"


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------


def test_enroll_happy_path(box: Box) -> None:
    res = run(box, "enroll", "--yes")  # one LUKS2 device: no --device needed
    assert res.returncode == 0, res.stderr + res.stdout
    calls = box.calls

    # read-only preflight (lsblk) first; libfido2 only after the confirmation; the
    # snapshot BEFORE any other change
    pkg = "omarchy-pkg-add libfido2"
    assert pkg in calls and "fido2-token -L" in calls and "omarchy-snapshot create" in calls
    assert calls.index("lsblk -rno PATH,FSTYPE,FSVER,UUID") < calls.index(pkg)
    enroll = f"systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes {DEV}"
    assert enroll in calls
    assert calls.index(pkg) < calls.index("omarchy-snapshot create") < calls.index(enroll)
    assert has_fido2_slot(box)

    # the rebuild is limine-mkinitcpio alone: it runs mkinitcpio for every kernel itself
    # (limine-mkinitcpio-install), and the mkinitcpio on Omarchy's PATH is limine's
    # interactive wrapper
    assert "limine-mkinitcpio" in calls
    assert calls.index(enroll) < calls.index("limine-mkinitcpio")
    assert not any(c.startswith("mkinitcpio") for c in calls)
    assert not any("wipe-slot" in c for c in calls)

    # the mkinitcpio drop-in, sorted after Omarchy's own, with the revert path in its header
    assert box.dropin.is_file()
    assert "hyprconf-yubikey disable" in box.dropin.read_text()
    assert sorted(p.name for p in box.mkinitcpio_d.iterdir())[-1] == box.dropin.name

    # the cmdline goes through limine-entry-tool's drop-in dir, beside Omarchy's own
    # resume.conf — the exact one line, nothing else
    assert box.limine_dropin.read_text() == LIMINE_DROPIN
    assert sorted(p.name for p in box.conf_d.iterdir()) == [*box.omarchy_conf_d, DROPIN_NAME]
    assert f"{box.limine_dropin}: written" in res.stdout

    # /etc/default/limine is never edited, and never named to a root command
    assert box.limine.read_text() == box.limine_file
    assert not any(str(box.limine) in c for c in calls), "no root command ever names the file"

    # the mapper name is asked of limine, not parsed out of a config layer, and the
    # drop-in is proven to reach the kernel before the hooks drop-in is written
    assert ran_as_root(box, "limine-entry-tool --get-cmdline default")
    assert "the drop-in reaches it" in res.stdout
    assert "Boot images rebuilt" in res.stdout
    assert "Done." in res.stdout and "passphrase" in res.stdout.lower()
    assert res.stdout.index("reaches it") < res.stdout.index("Done.")


def test_enroll_rerun_is_idempotent(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    dropin_first = box.dropin.read_text()
    box.reset()

    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls
    assert not any(c.startswith("systemd-cryptenroll") for c in calls), "slot already present"
    assert "limine-mkinitcpio" in calls
    assert f"{box.limine_dropin}: already in place" in res.stdout
    assert box.limine_dropin.read_text() == LIMINE_DROPIN
    assert box.dropin.read_text() == dropin_first
    assert box.limine.read_text() == box.limine_file


def test_enroll_refuses_luks1(box: Box) -> None:
    box.lsblk = LSBLK_STOCK.replace(f"{DEV} crypto_LUKS 2 {UUID}", f"{DEV} crypto_LUKS 1 {UUID}")
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "LUKS2" in res.stderr
    _assert_untouched(box)


def test_enroll_without_token_touches_nothing(box: Box) -> None:
    """libfido2 (which fido2-token comes from) is the one install before the token
    check; everything else stays untouched."""
    box.tokens = ""
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "fido2-token" in res.stderr
    assert set(c for c in box.calls if "limine-entry-tool" not in c) <= {
        "lsblk -rno PATH,FSTYPE,FSVER,UUID",
        f"lsblk -rno NAME,TYPE -- {DEV}",
        "findmnt -no SOURCE --nofsroot /",
        "omarchy-pkg-add libfido2",
        "fido2-token -L",
    }
    _assert_untouched(box, allow=("omarchy-pkg-add",))


@pytest.mark.parametrize(
    ("sub", "enrolled"),
    [("enroll", False), ("disable", True), ("remove", False)],
)
def test_refuses_without_tty_or_yes(box: Box, sub: str, enrolled: bool) -> None:
    """Without a terminal and without --yes the run dies at the confirmation — and
    NOTHING that changes anything ran before it, omarchy-pkg-add included. An enrolled
    box stays as it is."""
    if enrolled:
        assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
        box.reset()
    res = run(box, sub, "--device", DEV)
    assert res.returncode != 0
    assert "--yes" in res.stderr
    for name in ("omarchy-pkg-add", "systemd-cryptenroll", "limine-mkinitcpio", "omarchy-snapshot"):
        assert not any(c.startswith(name) for c in box.calls), box.calls
    assert has_fido2_slot(box) is enrolled
    assert box.dropin.exists() is enrolled and box.limine_dropin.exists() is enrolled
    if not enrolled:
        _assert_untouched(box)


def test_enroll_needs_device_flag_when_several(box: Box) -> None:
    """Several LUKS2 devices: --device, never a menu — a boot config is not something
    to pick by number in the dark. Also on a terminal."""
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 2 {UUID2}\n"
    res = run(box, "enroll", "--yes")
    assert res.returncode != 0 and "--device" in res.stderr
    assert DEV in res.stderr and "/dev/sdd" in res.stderr
    _assert_untouched(box)

    res = run(box, "enroll", assume_tty=True, stdin_text="2\ny\n")
    assert res.returncode != 0 and "--device" in res.stderr
    _assert_untouched(box)

    res = run(box, "enroll", "--yes", "--device", "/dev/sdz")
    assert res.returncode != 0 and "/dev/sdz" in res.stderr
    _assert_untouched(box)


def test_enroll_aborts_when_snapshot_fails(box: Box) -> None:
    box.snapshot_rc = 1
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0 and "--no-snapshot" in res.stderr
    _assert_untouched(box, allow=("omarchy-snapshot", "omarchy-pkg-add"))

    box.snapshot_rc = 127  # omarchy-snapshot: snapper not installed
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "snapper" in res.stderr and has_fido2_slot(box)


# ---------------------------------------------------------------------------
# The kernel cmdline: asked of limine-entry-tool, never parsed out of the layers
# ---------------------------------------------------------------------------

CRYPT = "cryptdevice=UUID=x:root root=/dev/mapper/root rw"
CMDLINE_SHAPES = [
    pytest.param(CMDLINE, "root", id="stock"),
    pytest.param(
        f"{CRYPT} rd.luks.name={UUID2}=data rd.luks.options={UUID2}=discard",
        "root",
        id="rd.luks-of-another-uuid",
    ),
    pytest.param(
        "cryptdevice=UUID=x:cryptroot root=/dev/mapper/cryptroot rw",
        "cryptroot",
        id="mapper-name-from-both",
    ),
    pytest.param("root=/dev/mapper/vault rw", "vault", id="mapper-name-from-root-alone"),
    pytest.param("cryptdevice=UUID=x:vault rw", "vault", id="mapper-name-from-cryptdevice-alone"),
    pytest.param(
        f"{CRYPT} rd.luks.name={UUID}=root",
        "root",
        id="matching-rd.luks.name-without-options-tolerated",
    ),
    # systemd-cryptsetup-generator(8)'s UUID-less global form: not a per-device
    # competitor, so tolerated and left alone
    pytest.param(
        f"{CRYPT} rd.luks.options=fido2-device=auto",
        "root",
        id="uuid-less-global-rd.luks.options-tolerated",
    ),
]


@pytest.mark.parametrize(("cmdline", "mapper"), CMDLINE_SHAPES)
def test_cmdline_shapes(box: Box, cmdline: str, mapper: str) -> None:
    box.base_cmdline = cmdline
    set_mapper(box, mapper)
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    _assert_configured(box, mapper)


REFUSED_CMDLINES = [
    pytest.param(
        "cryptdevice=UUID=x:root root=/dev/mapper/cryptroot rw",
        "root=/dev/mapper/cryptroot",
        id="cryptdevice-and-root-disagree",
    ),
    pytest.param(
        f"{CRYPT} rd.luks.name={UUID}=other",
        f"rd.luks.name={UUID}=other",
        id="rd.luks.name-for-uuid-names-another-mapper",
    ),
    pytest.param(
        f"{CRYPT} rd.luks.options={UUID}=discard",
        "would override the drop-in",
        id="rd.luks.options-for-uuid-would-override-the-dropin",
    ),
    pytest.param("root=UUID=y rw", "cannot tell", id="no-cryptdevice-no-mapper-root"),
    pytest.param("", "printed nothing", id="limine-says-nothing"),
]


@pytest.mark.parametrize(("cmdline", "reason"), REFUSED_CMDLINES)
def test_cmdline_refused_before_anything_changes(box: Box, cmdline: str, reason: str) -> None:
    """A cmdline whose parameters would fight the drop-in, or that does not say what the
    root is opened as, stops enroll before the confirmation: no package, slot, drop-in,
    edit."""
    if cmdline:
        box.base_cmdline = cmdline
    else:
        box.cmdline_silent = "1"  # limine-entry-tool answers with nothing at all
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert reason in res.stderr, res.stderr
    _assert_untouched(box)


def test_enroll_refuses_a_mapper_the_picked_device_is_not_open_as(box: Box) -> None:
    """The name comes off the cmdline; the device comes from --device. A data volume
    must never be handed the root's rd.luks.name= — the initramfs would unlock it
    instead. Both cross-checks refuse, independently."""
    box.crypt_child = "data"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "open as /dev/mapper/data" in res.stderr and "--device" in res.stderr
    _assert_untouched(box)

    box.crypt_child = ""  # the device is not open: nothing to compare it against
    box.root_source = "/dev/mapper/somethingelse"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "running from /dev/mapper/somethingelse" in res.stderr
    _assert_untouched(box)

    box.root_source = "/dev/sda2"  # a root that is not on /dev/mapper says nothing
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0


def test_enroll_refuses_a_competing_rd_luks_options_in_another_dropin(box: Box) -> None:
    """/etc/default/limine's own line is clean, but another /etc/limine-entry-tool.d/*.conf
    already sets rd.luks.options= for the device. systemd keeps one per device, and the
    assembled cmdline is the only place that shows it — a per-file read cannot say which
    layer wins, so the file is only named as a hint."""
    (box.conf_d / "zz-other.conf").write_text(
        f'KERNEL_CMDLINE[default]+=" rd.luks.options={UUID}=discard"\n'
    )
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert f"rd.luks.options={UUID}=discard" in res.stderr
    assert "would override the drop-in" in res.stderr
    assert str(box.conf_d / "zz-other.conf") in res.stderr
    _assert_untouched(box)


def test_enroll_names_the_inline_residue_when_it_is_on_etc_default_limine(box: Box) -> None:
    """The v4.0.0-4.2.0 layout (rd.luks.* inline on /etc/default/limine, no cmdline
    drop-in) is refused with what put it there and what to do."""
    set_limine_line(box, f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=root {RD_OPTS}"')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert str(box.limine) in res.stderr
    assert "4.0.0-4.2.0" in res.stderr and "keep cryptdevice=" in res.stderr
    _assert_untouched(box)


def test_enroll_refuses_a_plain_assignment_in_etc_default_limine(box: Box) -> None:
    """`KERNEL_CMDLINE[default]=` there replaces every drop-in's parameters, Omarchy's
    included (/etc/limine-entry-tool.conf:38-43), so the drop-in could never reach the
    kernel. One grep, before anything changes."""
    set_limine_line(box, f'KERNEL_CMDLINE[default]="{CMDLINE}"')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "make it += first" in res.stderr and str(box.limine) in res.stderr
    _assert_untouched(box)


def test_enroll_stops_at_the_cmdline_proof_when_the_dropin_does_not_reach_the_kernel(
    box: Box,
) -> None:
    """The general net behind that grep: whatever the reason, if limine does not hand
    the parameters to the kernel, the hooks drop-in is never written — what is on disk
    is the inert state, rd.luks.* the busybox initramfs ignores."""
    box.frozen_cmdline = CMDLINE  # limine never reports the drop-in, whatever the reason
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "is not on the cmdline limine assembles" in res.stderr
    assert "hyprconf-yubikey disable" in res.stderr
    assert box.limine_dropin.read_text() == LIMINE_DROPIN
    assert not box.dropin.exists(), "the hooks drop-in is the dangerous half"
    assert not any(c.startswith("limine-mkinitcpio") for c in box.calls)


# ---------------------------------------------------------------------------
# disable and remove never read the cmdline
# ---------------------------------------------------------------------------


def test_disable_and_remove_never_read_the_cmdline(box: Box) -> None:
    """Only enroll needs it (the mapper name comes from it). disable and remove touch
    nothing but the two drop-ins, so neither asks limine anything, and
    /etc/default/limine stays byte-identical."""
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.reset()
    res = run(box, "disable", "--yes", "--no-snapshot")
    assert res.returncode == 0, res.stderr
    assert "limine-entry-tool" not in box.commands
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file

    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.limine.write_text('ESP_PATH="/boot"\n')  # no cmdline line at all
    box.reset()
    res = run(box, "remove", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "limine-entry-tool" not in box.commands
    assert not has_fido2_slot(box) and not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == 'ESP_PATH="/boot"\n'


# ---------------------------------------------------------------------------
# The rebuild: limine-mkinitcpio exits 0 whatever mkinitcpio did
# ---------------------------------------------------------------------------


def test_rebuild_dies_on_limine_mkinitcpios_failure_message(box: Box) -> None:
    """The exact error_msg limine-mkinitcpio-install prints (:202), on stderr, with
    limine-mkinitcpio still exiting 0 — the previous image stays and still boots."""
    box.limine_mkinitcpio = "fail"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert BUILD_FAILED in res.stderr, "limine-mkinitcpio's output is shown"
    assert "previous one and still boots" in res.stderr
    assert "sudo limine-mkinitcpio" in res.stderr
    assert "Done." not in res.stdout and "Boot images rebuilt" not in res.stdout
    # the config changes are in place — that is what the retry rebuilds
    assert box.dropin.exists() and box.limine_dropin.read_text() == LIMINE_DROPIN


def test_rebuild_dies_on_limine_mkinitcpio_exit_code(box: Box) -> None:
    box.limine_mkinitcpio = "exit1"
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert "limine-mkinitcpio exited 1" in res.stderr and "sudo limine-mkinitcpio" in res.stderr
    assert "Done." not in res.stdout


# ---------------------------------------------------------------------------
# The keyboard-layout guard Omarchy's omarchy_hooks.conf has and sd-vconsole lacks
# ---------------------------------------------------------------------------


def test_the_non_latin_layout_list_is_the_tools_own() -> None:
    """The list cannot be derived at run time — its home,
    /etc/mkinitcpio.conf.d/omarchy_hooks.conf, is not under $OMARCHY_PATH and the suites
    must pass with no Omarchy at all — so the copy above is pinned against the tool's
    case line here, whole, instead of one subprocess per layout below."""
    assert " | ".join(NON_LATIN) + ") ;;" in TOOL.read_text()


@pytest.mark.parametrize("layout", ["ru", "ara"])
def test_enroll_refuses_non_latin_first_layout(box: Box, layout: str) -> None:
    box.vconsole.write_text(f'KEYMAP=us\nXKBLAYOUT="{layout},us"\n')
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode != 0
    assert layout in res.stderr and "--allow-non-latin-layout" in res.stderr
    assert box.calls == [], "refused before the device pick, the install, anything"
    _assert_untouched(box)


def test_enroll_allow_non_latin_layout_flag_warns_and_proceeds(box: Box) -> None:
    box.vconsole.write_text("KEYMAP=ru\nXKBLAYOUT=ru\n")
    res = run(box, "enroll", "--yes", "--device", DEV, "--allow-non-latin-layout")
    assert res.returncode == 0, res.stderr
    assert "warning" in res.stderr and "ru" in res.stderr and "passphrase" in res.stderr
    assert has_fido2_slot(box) and box.dropin.exists()


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
    res = run(box, "enroll", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    assert "warning" not in res.stderr


# ---------------------------------------------------------------------------
# The drop-in, sourced the way mkinitcpio sources it
# ---------------------------------------------------------------------------


def _source_dropin(box: Box, hooks: str, *, sd_overlay: bool = True) -> list[str]:
    """The drop-in carries the real /usr/lib/initcpio/install path (it is root-sourced at
    every rebuild, so no test seam may ship inside it): swap it for the box's fake
    directory, or for one that holds no sd-btrfs-overlayfs."""
    fake = box.initcpio_install if sd_overlay else box.tmp / "no-initcpio-install"
    fake.mkdir(exist_ok=True)
    body = box.dropin.read_text().replace(INITCPIO_INSTALL, str(fake))
    swapped = box.tmp / "dropin-under-test.conf"
    swapped.write_text(body)
    script = (
        "set -u\n"
        f"HOOKS=({hooks})\n"
        f'source "{swapped}"\n'
        "declare -p _hyprconf_hooks _hyprconf_hook >/dev/null 2>&1 && echo LEAKED\n"
        "printf '%s\\n' \"${HOOKS[@]}\"\n"
    )
    res = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env={"PATH": box.env["PATH"]}
    )
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert "LEAKED" not in lines, "the drop-in must unset its temporaries"
    return lines


def test_dropin_rewrites_omarchy_hooks(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    assert INITCPIO_INSTALL in box.dropin.read_text(), "no test seam ships into /etc"

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
    assert _source_dropin(box, " ".join(hooks)) == hooks


def test_dropin_keeps_busybox_overlay_hook_without_sd_variant(box: Box) -> None:
    """Older limine-mkinitcpio-hook without sd-btrfs-overlayfs: keep the busybox hook
    (harmless under systemd) rather than name a hook that does not exist. The test is
    made at every rebuild, against the real path — that is why it is not decided once
    at enroll time."""
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    hooks = _source_dropin(box, OMARCHY_HOOKS, sd_overlay=False)
    assert hooks[-1] == "btrfs-overlayfs" and "sd-btrfs-overlayfs" not in hooks
    assert "systemd" in hooks and "sd-encrypt" in hooks


def test_shellcheck_dropin(box: Box) -> None:
    """The drop-in is generated, so this is the only shellcheck it gets (the tool itself
    is covered by `make shellcheck`)."""
    shellcheck = shutil.which("shellcheck") or pytest.skip("shellcheck is not installed")
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    res = subprocess.run(
        [shellcheck, "--severity=warning", str(box.dropin)], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# disable / remove
# ---------------------------------------------------------------------------


def test_disable_removes_both_dropins(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.reset()

    res = run(box, "disable", "--yes")
    assert res.returncode == 0, res.stderr
    calls = box.calls
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert f"{box.limine_dropin}: removed" in res.stdout
    assert ran_as_root(box, f"rm -f -- {box.limine_dropin}")
    assert box.limine.read_text() == box.limine_file
    assert "omarchy-snapshot create" in calls
    assert "limine-mkinitcpio" in calls
    assert "Boot images rebuilt" in res.stdout
    assert not any(c.startswith("systemd-cryptenroll") for c in calls)
    assert has_fido2_slot(box), "disable keeps the LUKS slot"
    assert (box.mkinitcpio_d / "omarchy_hooks.conf").exists(), "Omarchy's own drop-ins stay"
    assert sorted(p.name for p in box.conf_d.iterdir()) == box.omarchy_conf_d


def test_disable_when_not_configured_changes_nothing(box: Box) -> None:
    """With snapshots ON: neither drop-in exists, so there is nothing to roll back and
    omarchy-snapshot is never called for the no-op."""
    res = run(box, "disable", "--yes")
    assert res.returncode == 0, res.stderr
    assert box.calls == []
    assert "Nothing to rebuild" in res.stdout
    assert box.limine.read_text() == box.limine_file


def test_remove_wipes_fido2_slot_then_disables(box: Box) -> None:
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.reset()

    res = run(box, "remove", "--yes", "--device", DEV)
    assert res.returncode == 0, res.stderr
    calls = box.calls
    wipe = f"systemd-cryptenroll --wipe-slot=fido2 {DEV}"
    assert wipe in calls
    assert calls.index(wipe) < calls.index("limine-mkinitcpio")
    assert not any("password" in c for c in calls), "passphrase slots are never touched"
    assert not has_fido2_slot(box)
    assert not box.dropin.exists() and not box.limine_dropin.exists()
    assert box.limine.read_text() == box.limine_file


# ---------------------------------------------------------------------------
# status / help / sudo
# ---------------------------------------------------------------------------


def test_status_prints_facts(box: Box) -> None:
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS 1 {UUID2}\n"

    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert f"{DEV}  LUKS2  UUID {UUID}  systemd-fido2 slot: no" in out
    assert "/dev/sdd  LUKS1" in out and "not eligible" in out
    assert f"initramfs drop-in: absent ({box.dropin})" in unpadded(out)
    assert f"cmdline drop-in: absent ({box.limine_dropin})" in unpadded(out)
    assert "kernel cmdline: no rd.luks.* parameters" in unpadded(out)
    assert f"plugged in — {TOKEN_LINE}" in out
    assert "sd-btrfs-overlayfs installed" in out
    for name in ("systemd-cryptenroll", "limine-mkinitcpio", "omarchy-snapshot", "mkinitcpio"):
        assert not any(c.startswith(name) for c in box.calls)

    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    box.tokens = ""
    res = run(box)  # status is the default subcommand
    assert res.returncode == 0
    assert "systemd-fido2 slot: yes" in res.stdout
    assert f"initramfs drop-in: present ({box.dropin})" in unpadded(res.stdout)
    assert f"cmdline drop-in: present ({box.limine_dropin})" in unpadded(res.stdout)
    assert f"kernel cmdline: rd.luks.name={UUID}=root {RD_OPTS}" in unpadded(res.stdout)
    assert "set outside" not in res.stdout
    assert "FIDO2 token: none detected" in unpadded(res.stdout)


def test_status_reports_rd_luks_set_outside_the_dropin(box: Box) -> None:
    """A box enrolled by hyprconf-yubikey 4.0.0-4.2.0 carries the two parameters inline
    on /etc/default/limine; `disable` never touches that file (README › Undo), so status
    names where they are written instead of reporting a clean cmdline."""
    set_limine_line(box, f'KERNEL_CMDLINE[default]+="{CRYPT} rd.luks.name={UUID}=root {RD_OPTS}"')
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    out = unpadded(res.stdout)
    assert f"kernel cmdline: rd.luks.name={UUID}=root {RD_OPTS}" in out
    assert "set outside" in out and str(box.limine) in out
    assert "4.0.0-4.2.0" in out and "keep cryptdevice=" in out


def test_status_says_unknown_instead_of_asking_sudo_per_device(box: Box) -> None:
    """Without usable sudo credentials every LUKS2 row and the cmdline read "unknown
    (run as root)" and status still exits 0 — and the tool asks sudo once for the whole
    listing, not once per privileged read (each `sudo -n` writes an auth-log record)."""
    for name in ("sudo", "cryptsetup"):
        box.stub(name, "exit 1\n")
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    assert f"{DEV}  LUKS2  UUID {UUID}  systemd-fido2 slot: unknown (run as root)" in res.stdout
    assert "kernel cmdline: unknown (run as root" in unpadded(res.stdout)
    assert [c for c in box.calls if c.startswith("sudo")] == ["sudo -n -- true"]


def test_status_never_fails(box: Box) -> None:
    drop_sd_overlay(box)
    box.limine.unlink()
    box.lsblk = ""
    res = run(box, "status")
    assert res.returncode == 0, res.stderr
    assert "none found" in res.stdout
    assert "sd-btrfs-overlayfs NOT installed" in res.stdout


def test_help_documents_flags_limitations_and_revert(box: Box) -> None:
    res = run(box, "help")
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
    assert "hyprconf-yubikey disable" in out and "hyprconf-yubikey remove" in out
    assert run(box, "--help").returncode == 0
    assert run(box, "bogus").returncode != 0
    assert run(box, "enroll", "--enrol").returncode != 0, "one spelling per flag"
    assert box.calls == []


def test_sudo_subcommand_execs_omarchy_script(box: Box) -> None:
    res = run(box, "sudo")
    assert res.returncode == 0, res.stderr
    assert "OMARCHY FIDO2 SETUP" in res.stdout
    assert box.calls == ["omarchy-setup-security-fido2"]


# ---------------------------------------------------------------------------
# Audit pins: field round-trips, write order, the one prompt
# ---------------------------------------------------------------------------


def test_empty_fsver_luks_row_reads_as_unknown_version(box: Box) -> None:
    """lsblk leaves FSVER empty when blkid cannot tell. The empty field must survive the
    awk-to-read round trip — whitespace-delimited it collapsed, and the UUID became the
    'version' in every diagnostic."""
    box.lsblk = LSBLK_STOCK + f"/dev/sdd crypto_LUKS  {UUID2}\n"
    res = run(box, "enroll", "--yes", "--device", "/dev/sdd")
    assert res.returncode == 1
    assert "is LUKS? — systemd-cryptenroll needs LUKS2" in res.stderr


def test_enroll_writes_the_cmdline_dropin_before_the_hooks_dropin(box: Box) -> None:
    """The inert intermediate state must come first: rd.luks.* without the systemd hooks
    is ignored by the busybox initramfs, but the hooks drop-in without rd.luks.* turns
    the next kernel upgrade's rebuild into an initramfs that cannot unlock the root."""
    assert run(box, "enroll", "--yes", "--device", DEV).returncode == 0
    calls = box.calls
    limine_i = next(i for i, c in enumerate(calls) if "tee" in c and str(box.limine_dropin) in c)
    hooks_i = next(i for i, c in enumerate(calls) if "tee" in c and str(box.dropin) in c)
    assert limine_i < hooks_i


def test_interactive_confirm_n_aborts_untouched(box: Box) -> None:
    res = run(box, "enroll", "--device", DEV, assume_tty=True, stdin_text="n\n")
    assert res.returncode == 1
    assert "aborted — nothing changed" in res.stderr
    assert not box.dropin.exists() and not box.limine_dropin.exists()
