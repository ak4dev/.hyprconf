"""
Tests for setup.sh's screen-locker PAM shields.

A Wayland lock screen authenticates as the *session user*, never root, so two
PAM states are an unrecoverable lockout of a running session:

  · no /etc/pam.d/<service> at all — PAM falls back to /etc/pam.d/other
    (pam_deny) and the locker can never authenticate anybody.  Arch ships no
    /etc/pam.d/cosmic-greeter, so COSMIC's lock screen is broken on install;
  · a stack carrying pam_u2f, directly or inherited via `include login` once
    yubikey-fido2-setup has added the key to /etc/pam.d/login.  Because
    /etc/security/u2f_keys is 0640 root:root, pam_u2f's open() gets EACCES as
    the session user and it returns PAM_AUTHINFO_UNAVAIL, rejecting every
    unlock with the key inserted or not.

The hazard detector is exercised behaviourally against fixtures; the wiring is
asserted statically.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"


def _text() -> str:
    return SETUP_SH.read_text(encoding="utf-8")


def _extract_function(name: str) -> str:
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\) \\{{/,/^}}$/", str(SETUP_SH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _is_hazardous(stack: str, login_stack: str = "", home: str | None = None) -> bool:
    """Run the real _locker_pam_is_hazardous() against fixture files.

    Every collaborating function is injected — extracting only the entry point
    would leave the helpers undefined, and `command not found` would silently
    read as "safe".  HOME is overridden so the per-user authfile fallback
    resolves into the fixture tree instead of the developer's real home.
    """
    fragment = "\n".join(
        [
            "set -uo pipefail",
            _extract_function("_pam_u2f_line"),
            _extract_function("_pam_u2f_authfile_of"),
            _extract_function("_authfile_readable_by_user"),
            _extract_function("_locker_pam_is_hazardous"),
            f'_locker_pam_is_hazardous "{stack}" "{login_stack}" && echo HAZARD || echo SAFE',
        ]
    )
    env = {**os.environ, "HOME": home or "/nonexistent-home"}
    env.pop("XDG_CONFIG_HOME", None)
    out = subprocess.run(
        ["bash", "-c", fragment], capture_output=True, text=True, timeout=30, env=env
    ).stdout
    return "HAZARD" in out


def _authfile(tmp_path: Path, *, readable: bool) -> Path:
    """An authfile the running test user can, or cannot, read."""
    path = tmp_path / ("readable_keys" if readable else "unreadable_keys")
    path.write_text("andy:credential\n")
    path.chmod(0o644 if readable else 0o000)
    return path


# ---------------------------------------------------------------------------
# Hazard detection — behavioural
# ---------------------------------------------------------------------------

PASSWORD_ONLY = "# Managed by hyprconf\nauth        include     system-auth\n"


def test_password_only_stack_is_safe(tmp_path: Path) -> None:
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(PASSWORD_ONLY)
    assert not _is_hazardous(str(stack))


def test_pam_u2f_with_unreadable_authfile_is_hazardous(tmp_path: Path) -> None:
    """The observed COSMIC failure: pam_u2f can't open the authfile as the
    session user, returns PAM_AUTHINFO_UNAVAIL, and no unlock ever succeeds."""
    keys = _authfile(tmp_path, readable=False)
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(f"auth required pam_u2f.so authfile={keys} cue\n")
    assert _is_hazardous(str(stack))


def test_pam_u2f_with_missing_authfile_is_hazardous(tmp_path: Path) -> None:
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(f"auth required pam_u2f.so authfile={tmp_path / 'absent'} cue\n")
    assert _is_hazardous(str(stack))


def test_pam_u2f_with_readable_authfile_is_left_alone(tmp_path: Path) -> None:
    """A deliberate, working 2FA locker must NOT be silently downgraded to
    password-only by an unattended sync — that would weaken a setup the user
    chose on purpose."""
    keys = _authfile(tmp_path, readable=True)
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(f"auth required pam_u2f.so authfile={keys} cue\n")
    assert not _is_hazardous(str(stack))


def _seed_per_user_authfile(home: Path) -> None:
    keys = home / ".config" / "Yubico" / "u2f_keys"
    keys.parent.mkdir(parents=True, exist_ok=True)
    keys.write_text("andy:credential\n")
    keys.chmod(0o600)


def test_pam_u2f_with_enrolled_per_user_authfile_is_left_alone(tmp_path: Path) -> None:
    """No authfile= means pam_u2f reads a per-user path under $HOME. When the
    user is actually enrolled there, that is a working 2FA locker."""
    home = tmp_path / "home"
    home.mkdir()
    _seed_per_user_authfile(home)
    stack = tmp_path / "cosmic-greeter"
    stack.write_text("auth required pam_u2f.so cue\n")
    assert not _is_hazardous(str(stack), home=str(home))


def test_pam_u2f_with_absent_per_user_authfile_is_hazardous(tmp_path: Path) -> None:
    """Nothing enrolled and no nouserok: pam_u2f returns PAM_AUTHINFO_UNAVAIL
    and the `required` stack rejects every unlock."""
    home = tmp_path / "home"
    home.mkdir()
    stack = tmp_path / "cosmic-greeter"
    stack.write_text("auth required pam_u2f.so cue\n")
    assert _is_hazardous(str(stack), home=str(home))


def test_nouserok_rescues_an_absent_authfile(tmp_path: Path) -> None:
    """pam-u2f downgrades a *missing* authfile to PAM_IGNORE under nouserok, so
    the stack falls through to the password and the screen still opens."""
    home = tmp_path / "home"
    home.mkdir()
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(f"auth required pam_u2f.so authfile={tmp_path / 'absent'} nouserok\n")
    assert not _is_hazardous(str(stack), home=str(home))


def test_nouserok_does_not_rescue_an_unreadable_authfile(tmp_path: Path) -> None:
    """util.c downgrades ENOENT only — EACCES still yields
    PAM_AUTHINFO_UNAVAIL, which is exactly the observed COSMIC failure."""
    keys = _authfile(tmp_path, readable=False)
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(f"auth required pam_u2f.so authfile={keys} nouserok\n")
    assert _is_hazardous(str(stack))


def test_commented_pam_u2f_is_safe(tmp_path: Path) -> None:
    """The shield we write *documents* pam_u2f in comments — that must not
    re-trigger a rewrite on every sync, or the run is never idempotent."""
    stack = tmp_path / "cosmic-greeter"
    stack.write_text(
        "# Do NOT add pam_u2f.so here or `include login`: it would lock you out.\n"
        "auth        include     system-auth\n"
    )
    assert not _is_hazardous(str(stack))


def test_include_login_is_hazardous_when_inherited_authfile_is_unreadable(
    tmp_path: Path,
) -> None:
    keys = _authfile(tmp_path, readable=False)
    login = tmp_path / "login"
    login.write_text(f"auth required pam_u2f.so authfile={keys}\nauth include system-auth\n")
    stack = tmp_path / "hyprlock"
    stack.write_text("auth include login\n")
    assert _is_hazardous(str(stack), str(login))


def test_include_login_is_left_alone_when_inherited_authfile_is_readable(
    tmp_path: Path,
) -> None:
    keys = _authfile(tmp_path, readable=True)
    login = tmp_path / "login"
    login.write_text(f"auth required pam_u2f.so authfile={keys}\nauth include system-auth\n")
    stack = tmp_path / "hyprlock"
    stack.write_text("auth include login\n")
    assert not _is_hazardous(str(stack), str(login))


def test_include_login_is_safe_when_login_has_no_key(tmp_path: Path) -> None:
    """Without the YubiKey line there is nothing to inherit, so an untouched
    distro locker config is left alone rather than needlessly rewritten."""
    login = tmp_path / "login"
    login.write_text("auth include system-auth\n")
    stack = tmp_path / "hyprlock"
    stack.write_text("auth include login\n")
    assert not _is_hazardous(str(stack), str(login))


def test_missing_login_stack_is_not_hazardous(tmp_path: Path) -> None:
    stack = tmp_path / "hyprlock"
    stack.write_text("auth include login\n")
    assert not _is_hazardous(str(stack), str(tmp_path / "no-such-login"))


# ---------------------------------------------------------------------------
# Wiring — static
# ---------------------------------------------------------------------------


def test_cosmic_greeter_is_a_managed_locker() -> None:
    """COSMIC's lock screen calls pam_start("cosmic-greeter") unprivileged."""
    match = re.search(r"HYPRCONF_LOCKER_PAM=\(([^)]*)\)", _text(), re.DOTALL)
    assert match, "HYPRCONF_LOCKER_PAM array not found"
    entries = match.group(1).split()
    services = [e.strip('"').split(":")[0] for e in entries]
    assert "cosmic-greeter" in services, "COSMIC's locker must be managed"
    assert "hyprlock" in services


def test_locker_shield_emits_password_only_stack() -> None:
    body = _extract_function("_write_locker_pam")
    assert "system-auth" in body
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert "pam_u2f.so" not in stripped, f"shield must not activate pam_u2f: {line!r}"


def test_locker_shield_gates_on_locker_being_installed() -> None:
    """Never litter PAM files for software that isn't present."""
    body = _extract_function("ensure_locker_pam")
    assert 'command -v "$bin"' in body, "must skip lockers that aren't installed"


def test_locker_shield_backs_up_before_correcting() -> None:
    body = _extract_function("ensure_locker_pam")
    assert ".bak." in body, "an existing stack must be backed up before rewrite"


def test_locker_shield_runs_on_both_install_and_sync() -> None:
    """A locker installed after the system was built (COSMIC added later) must
    be repaired by the next `setup.sh --sync`, per the sync-patchable rule."""
    calls = [ln for ln in _text().splitlines() if ln.strip() == "ensure_locker_pam"]
    assert len(calls) >= 2, (
        "ensure_locker_pam must be called from both the install and --sync paths"
    )
