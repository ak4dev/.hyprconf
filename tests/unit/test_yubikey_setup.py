"""
Unit tests for yubikey-fido2-setup — the interactive YubiKey FIDO2+PIN login
setup script (stowed to ~/.local/bin).

All tests are static-analysis only: they assert the script is valid bash, is
reachable on a new system (lives under stow/, not the export-ignored scripts/),
and that the PAM / SSH / LUKS / bootloader wiring it ships matches the
documented behaviour. No root, hardware, or live system is required.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "yubikey-fido2-setup"
PACKAGES = REPO_ROOT / "packages"
README = REPO_ROOT / "README.md"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _func_body(name: str) -> str:
    """Extract a single shell function body via awk (matches existing test style)."""
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\) \\{{/,/^}}$/", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Reachability: must be stowed (so new systems get it), valid, and executable
# ---------------------------------------------------------------------------


def test_script_exists_in_stowed_bin() -> None:
    assert SCRIPT.exists(), (
        "yubikey-fido2-setup must live under stow/hypr/.local/bin so it is "
        "stowed onto new systems and on PATH — scripts/ is export-ignored and "
        "absent from the installer's sparse-checkout paths."
    )


def test_script_not_in_dev_only_scripts_dir() -> None:
    # scripts/ is export-ignored and not sparse-checked-out; the YubiKey helper
    # must not regress back into it.
    assert not (REPO_ROOT / "scripts" / "yubikey-fido2-setup.sh").exists()


def test_script_is_executable() -> None:
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "yubikey-fido2-setup must be executable"


def test_script_shebang() -> None:
    assert _text().startswith("#!/usr/bin/env bash\n")


def test_script_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


def test_script_has_pipefail_guard() -> None:
    # Deliberately `-uo pipefail` (not -e): the script relies on `|| die` plus an
    # ERR trap for interactive rollback, which `set -e` would short-circuit.
    assert "set -uo pipefail" in _text()


# ---------------------------------------------------------------------------
# Backup / rollback safety net
# ---------------------------------------------------------------------------


def test_backs_up_and_rolls_back() -> None:
    txt = _text()
    assert "backup()" in txt and "rollback()" in txt
    assert "BACKUP_DIR=" in txt
    # ERR trap offers rollback on unexpected failure
    assert "trap " in txt and "rollback" in txt


# ---------------------------------------------------------------------------
# Package handling — installs the same deps listed (commented) in `packages`
# ---------------------------------------------------------------------------


def test_installs_required_packages() -> None:
    txt = _text()
    for pkg in ("libfido2", "pam-u2f", "yubikey-manager"):
        assert pkg in txt, f"script must check/install {pkg}"


# ---------------------------------------------------------------------------
# Registration + PAM
# ---------------------------------------------------------------------------


def test_u2f_keys_path_and_perms() -> None:
    txt = _text()
    assert 'U2F_KEYS="/etc/security/u2f_keys"' in txt
    assert "chmod 640" in txt
    assert "chown root:root" in txt


def test_pam_line_uses_pin_verification_and_cue() -> None:
    txt = _text()
    assert "pam_u2f.so" in txt
    assert "pinverification=1" in txt
    assert "cue" in txt
    assert "authfile=/etc/security/u2f_keys" in txt


def test_pam_targets_sudo_login_dm_and_ssh() -> None:
    txt = _text()
    assert "/etc/pam.d/sudo" in txt
    assert "/etc/pam.d/login" in txt
    assert "/etc/pam.d/sshd" in txt
    # display managers are auto-detected
    for dm in ("sddm", "gdm", "lightdm"):
        assert dm in txt


def test_pam_insertion_is_idempotent() -> None:
    # pam_add_u2f skips files that already contain pam_u2f
    txt = _text()
    assert 'grep -q "pam_u2f.so"' in txt


# ---------------------------------------------------------------------------
# hyprlock is INTENTIONALLY left password-only — the script must never touch it
# ---------------------------------------------------------------------------


def test_shields_hyprlock_password_only() -> None:
    # hyprlock's packaged PAM config is `auth include login`, and the setup adds
    # pam_u2f (required) to /etc/pam.d/login — so it MUST rewrite
    # /etc/pam.d/hyprlock to authenticate against the untouched system-auth stack
    # (password only). Otherwise a missing/failed key makes the lock screen
    # impossible to unlock — a critical self-lockout.
    text = _text()
    assert "/etc/pam.d/hyprlock" in text, "setup must manage hyprlock's PAM config"
    body = _func_body("shield_hyprlock")
    assert "system-auth" in body, "hyprlock must authenticate against system-auth"
    assert "pam_u2f" not in body, "hyprlock must never include pam_u2f"


def test_configure_pam_shields_hyprlock() -> None:
    assert "shield_hyprlock" in _func_body("configure_pam"), (
        "configure_pam must call shield_hyprlock so the lock screen stays "
        "password-only after pam_u2f is added to /etc/pam.d/login"
    )


# ---------------------------------------------------------------------------
# SSH daemon hardening
# ---------------------------------------------------------------------------


def test_ssh_sets_pam_and_auth_methods() -> None:
    txt = _text()
    assert 'sshd_set "UsePAM" "yes"' in txt
    assert "AuthenticationMethods" in txt
    assert "keyboard-interactive" in txt
    # validates config before restarting
    assert "sshd -t" in txt
    assert "systemctl restart sshd" in txt


def test_ssh_handles_kbdinteractive_rename() -> None:
    # OpenSSH renamed ChallengeResponseAuthentication -> KbdInteractiveAuthentication in 8.7
    txt = _text()
    assert "KbdInteractiveAuthentication" in txt
    assert "ChallengeResponseAuthentication" in txt


# ---------------------------------------------------------------------------
# LUKS / boot unlock (must mirror this system's systemd-boot + sd-encrypt setup)
# ---------------------------------------------------------------------------


def test_luks_enrolls_fido2_via_cryptenroll() -> None:
    txt = _text()
    assert "systemd-cryptenroll" in txt
    assert "--fido2-device=auto" in txt
    assert "--fido2-with-client-pin=yes" in txt


def test_luks_requires_luks2() -> None:
    # systemd-cryptenroll needs LUKS2; the script filters to Version: 2 devices
    txt = _text()
    assert "luksDump" in txt
    assert "Version:" in txt


def test_crypttab_gets_fido2_option() -> None:
    assert "fido2-device=auto" in _text()
    assert "/etc/crypttab" in _text()


def test_mkinitcpio_converts_to_systemd_hooks() -> None:
    txt = _text()
    assert "sd-encrypt" in txt
    assert "sd-vconsole" in txt
    assert "mkinitcpio -P" in txt


def test_bootloader_param_and_both_loaders() -> None:
    txt = _text()
    assert "rd.luks.options=UUID=" in txt
    assert "fido2-device=auto" in txt
    # GRUB and systemd-boot are both handled
    assert "/etc/default/grub" in txt
    assert "/boot/loader/entries" in txt


# ---------------------------------------------------------------------------
# Repo wiring: packages + README parity
# ---------------------------------------------------------------------------


def test_packages_lists_yubikey_deps_commented() -> None:
    lines = PACKAGES.read_text(encoding="utf-8").splitlines()
    for pkg in ("libfido2", "pam-u2f", "yubikey-manager"):
        matches = [ln for ln in lines if pkg in ln]
        assert matches, f"{pkg} missing from packages"
        # optional hardware → must stay commented so non-YubiKey users skip it
        assert all(ln.lstrip().startswith("#") for ln in matches), (
            f"{pkg} must be commented (optional YubiKey hardware)"
        )


def test_readme_documents_script_and_hyprlock_exclusion() -> None:
    txt = README.read_text(encoding="utf-8")
    assert "yubikey-fido2-setup" in txt
    assert "systemd-cryptenroll" in txt
    # README must record that hyprlock stays password-only by design
    assert "hyprlock" in txt and "password-only" in txt


# ---------------------------------------------------------------------------
# Subcommand dispatch: setup / enroll / status
# ---------------------------------------------------------------------------


def test_main_dispatches_subcommands() -> None:
    txt = _text()
    for fn in ("do_setup()", "do_enroll()", "do_status()", "usage_yk()"):
        assert fn in txt, f"missing {fn}"
    # main() routes each action; bare/default is setup (back-compat)
    assert 'action="${1:-setup}"' in txt
    for token in ("setup|", "enroll|add", "status|list"):
        assert token in txt, f"main() must route {token}"


def test_enroll_appends_login_key_never_replaces() -> None:
    body = _func_body("enroll_login_key")
    assert body, "enroll_login_key must exist"
    # appends a credential to the existing user line (does not rewrite/replace it)
    assert "pamu2fcfg --pin-verification --nouser" in body
    assert "append_cred" in body
    # refuses to run before initial setup created the entry
    assert "run" in body and "setup" in body


def test_credential_append_does_not_use_sed() -> None:
    # pamu2fcfg output is base64 (contains '/' and '+'), which breaks sed's s///
    # delimiter. Credential appends must go through append_cred (python), never sed.
    txt = _text()
    assert "append_cred()" in txt
    assert "python3" in _func_body("append_cred")
    # no sed substitution that appends a credential variable to the user line
    import re

    bad = re.findall(r"sed -i .*s/\\?\$/:\$\{[a-z]*cred\}/", txt)
    assert not bad, f"credential append must not use sed: {bad}"


def test_log_uses_unique_file_and_tolerates_unwritable() -> None:
    txt = _text()
    # fixed /tmp/yubikey-setup.log is unwritable for root when a stale copy is
    # owned by another user (fs.protected_regular). Use a per-run mktemp file
    # and never let a failed log write abort the run.
    assert "mktemp" in txt
    assert 'tee -a "$LOG" 2>/dev/null || true' in txt


def test_backup_dir_uses_mktemp_not_predictable_path() -> None:
    txt = _text()
    # Root writes config backups into BACKUP_DIR; a predictable /tmp path could be
    # pre-created or symlinked by another user. It must be created atomically via
    # `mktemp -d` (0700, root-owned) rather than a guessable timestamped name.
    assert 'BACKUP_DIR="$(mktemp -d' in txt, (
        "BACKUP_DIR must be created with `mktemp -d` so the backup path cannot be "
        "hijacked (mirrors the LOG hardening)"
    )


def test_enroll_luks_adds_slot_without_initramfs_rebuild() -> None:
    body = _func_body("enroll_luks_key")
    assert body, "enroll_luks_key must exist"
    assert "systemd-cryptenroll" in body
    assert "--fido2-device=auto" in body
    # adding a slot must NOT rebuild initramfs or rewrite boot config — that is
    # only done by first-time setup (configure_luks/update_mkinitcpio).
    assert "mkinitcpio" not in body
    assert "update_bootloader" not in body
    assert "update_crypttab" not in body


def test_status_is_readonly_and_reports_slots() -> None:
    body = _func_body("do_status")
    assert body, "do_status must exist"
    # read-only: disables the rollback ERR trap, makes no edits
    assert "trap - ERR" in body
    assert "systemd-fido2" in body  # counts LUKS FIDO2 token slots
    assert "pam_u2f.so" in body  # reports PAM coverage
    assert "u2f_keys" in body.lower() or "U2F_KEYS" in body
    for verb in ("sed -i", "cryptenroll", "pamu2fcfg"):
        assert verb not in body, f"status must not call {verb} (read-only)"
