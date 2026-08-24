"""omarchy/install.sh — the overlay installer for Omarchy systems.

This installer is unusual for hyprconf in that it runs on a machine it does not
own: Omarchy owns the base system, and the overlay's whole design constraint is
to disturb it as little as possible. Most of what is asserted here is therefore
*restraint* — what the installer must NOT do:

  * never `chsh` (the login shell stays bash, so Omarchy's rc chain, aliases,
    completions, session and scripts keep working)
  * never rewrite Omarchy's ~/.config/kitty/kitty.conf beyond appending one
    `include` line (it owns the theme include, listen_on, font_family/font_size)
  * never reach `omarchy-launch-floating-terminal-with-presentation`, which
    `omarchy-default-terminal` exec()s when kitty is missing — a GUI window is
    fatal to a non-interactive run
  * never `pacman -Syu` (an Omarchy ALPM AbortOnFail hook blocks it) or
    `pacman -R` (on Omarchy the "foreign" set includes Omarchy itself)

Everything runs against fake `omarchy-*` binaries in a throwaway HOME, so the
suite is hermetic in a bare archlinux container per the testing rules.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OMARCHY_DIR = REPO_ROOT / "omarchy"
INSTALL_SH = OMARCHY_DIR / "install.sh"
HOOK = OMARCHY_DIR / "hooks" / "post-update.d" / "10-hyprconf"

# A recording stub: appends its own name + args to the calls log, then runs an
# optional body. One template covers every external the installer touches.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "${{0##*/}} $*" >> "{calls}"
{body}
"""

# Omarchy's kitty.conf as a fresh install has it (seeded from /etc/skel). The
# include, allow_remote_control/listen_on and font_family lines are exactly what
# the overlay must leave intact.
OMARCHY_KITTY_CONF = """include ~/.local/state/omarchy/current/theme/kitty.conf
allow_remote_control yes
listen_on unix:${XDG_RUNTIME_DIR}/omarchy-kitty-{kitty_pid}
font_family JetBrainsMono Nerd Font
font_size 10
"""


def _stub(path: Path, calls: Path, body: str = "exit 0") -> None:
    path.write_text(STUB.format(calls=calls, body=body))
    path.chmod(0o755)


def _setup(tmp_path: Path, *, with_omarchy: bool = True, with_zsh: bool = True) -> dict:
    """Build a throwaway HOME + fake-bins tree resembling a fresh Omarchy box."""
    home = tmp_path / "home"
    bins = tmp_path / "bins"
    omarchy_path = tmp_path / "omarchy"
    calls = tmp_path / "calls"
    for d in (home, bins, omarchy_path):
        d.mkdir(parents=True, exist_ok=True)
    calls.write_text("")

    for name in (
        "omarchy-theme-set",
        "omarchy-shell",
        "omarchy-plugin-enable",
        "omarchy-update",
        "hyprctl",
        "kitty",
        # Asserted never to run: the GUI path out of omarchy-default-terminal.
        "omarchy-launch-floating-terminal-with-presentation",
        # Asserted never to run: switching the login shell.
        "chsh",
    ):
        _stub(bins / name, calls)
    if with_omarchy:
        _stub(bins / "omarchy-pkg-add", calls)
    if with_zsh:
        _stub(bins / "zsh", calls)
    # No plugin is enabled yet, so the jq guard must fall through to enable.
    _stub(bins / "omarchy-plugin-list", calls, 'echo "[]"')
    _stub(bins / "jq", calls, "exit 1")
    # Reports foot until something sets it, then reports what was set.
    _stub(
        bins / "omarchy-default-terminal",
        calls,
        f'if [ $# -eq 0 ]; then cat "{tmp_path}/term" 2>/dev/null || echo foot;'
        f' else printf "%s" "$1" > "{tmp_path}/term"; fi',
    )
    # `clone` must materialise a directory; everything else is a no-op.
    _stub(bins / "git", calls, 'if [ "$1" = clone ]; then mkdir -p "${@: -1}"; fi; exit 0')

    # Seed the parts of a fresh Omarchy $HOME the installer interacts with.
    (home / ".config" / "kitty").mkdir(parents=True)
    (home / ".config" / "kitty" / "kitty.conf").write_text(OMARCHY_KITTY_CONF)
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "hypr" / "bindings.lua").write_text("-- stock omarchy bindings\n")
    (omarchy_path / "default" / "bash").mkdir(parents=True)

    return {"home": home, "bins": bins, "omarchy_path": omarchy_path, "calls": calls}


def _run(env: dict, *args: str, zsh: str | None = None) -> subprocess.CompletedProcess:
    """Run install.sh against the fake tree. Returns the completed process."""
    child_env = {
        "HOME": str(env["home"]),
        "PATH": f"{env['bins']}:/usr/bin:/bin",
        "OMARCHY_PATH": str(env["omarchy_path"]),
    }
    if zsh is not None:
        child_env["_HYPRCONF_ZSH"] = zsh
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=child_env,
    )


def _calls(env: dict) -> list[str]:
    return env["calls"].read_text().splitlines()


def _commands(env: dict) -> list[str]:
    """Just the command names invoked.

    Match on these, never on the whole call line: pytest names tmp dirs after
    the test, so a path baked into an argument can contain almost any word and
    produce a false positive.
    """
    return [c.split()[0] for c in _calls(env) if c.strip()]


def _code_only(body: str) -> str:
    """Drop comments so a static scan can't match a comment explaining the rule.

    Naive on `#` inside strings, which is fine for the forbidden-token scans
    below — none of them look for a character that appears in one.
    """
    out = []
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split(" #", 1)[0])
    return "\n".join(out)


def _tree_hash(root: Path) -> str:
    """Hash every path and file body under root, for byte-stability checks."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_symlink():
            h.update(b"->" + str(os.readlink(p)).encode())
        elif p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------


def test_scripts_are_syntactically_valid() -> None:
    for script in (INSTALL_SH, HOOK):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0, script


# ---------------------------------------------------------------------------
# Preflight — the guard that keeps this off a non-Omarchy machine
# ---------------------------------------------------------------------------


def test_refuses_without_omarchy_command(tmp_path: Path) -> None:
    env = _setup(tmp_path, with_omarchy=False)
    proc = _run(env)
    assert proc.returncode != 0
    assert "omarchy" in proc.stderr.lower()
    # Nothing may be written before the guard fires.
    assert not (env["home"] / ".zshrc").exists()


def test_refuses_without_omarchy_path(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    env["omarchy_path"] = tmp_path / "no-omarchy-here"  # never created
    proc = _run(env)
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# Idempotency — a re-run is the supported way to pick up changes
# ---------------------------------------------------------------------------


def test_full_run_succeeds_and_is_byte_stable(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    first = _run(env, "--no-update")
    assert first.returncode == 0, first.stderr

    after_first = _tree_hash(env["home"])
    assert _run(env, "--no-update").returncode == 0
    after_second = _tree_hash(env["home"])
    assert _run(env, "--no-update").returncode == 0
    after_third = _tree_hash(env["home"])

    assert after_first == after_second == after_third


def test_zshrc_block_has_exactly_one_marker_pair(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    for _ in range(3):
        _run(env, "--no-update")
    zshrc = (env["home"] / ".zshrc").read_text()
    assert zshrc.count("# >>> hyprconf >>>") == 1
    assert zshrc.count("# <<< hyprconf <<<") == 1


def test_zshrc_preserves_content_outside_the_block(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    (env["home"] / ".zshrc").write_text("export MY_OWN_THING=1\n")
    for _ in range(2):
        _run(env, "--no-update")
    assert "export MY_OWN_THING=1" in (env["home"] / ".zshrc").read_text()


# ---------------------------------------------------------------------------
# Restraint — what the installer must never do
# ---------------------------------------------------------------------------


def test_never_changes_the_login_shell(tmp_path: Path) -> None:
    """The hybrid's whole point: kitty runs zsh, the login shell stays bash."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert "chsh" not in _commands(env)
    assert "chsh" not in _code_only(INSTALL_SH.read_text())


def test_never_opens_the_floating_terminal(tmp_path: Path) -> None:
    """omarchy-default-terminal exec()s a GUI window when kitty is missing."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-launch-floating") for c in _commands(env))


def test_kitty_conf_gains_only_the_include(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    for _ in range(3):
        _run(env, "--no-update")
    conf = (env["home"] / ".config" / "kitty" / "kitty.conf").read_text()

    # Every original line survives, in order, untouched.
    assert conf.startswith(OMARCHY_KITTY_CONF)
    # And the only thing added is one include.
    assert conf.count("include hyprconf.conf") == 1
    added = conf[len(OMARCHY_KITTY_CONF) :]
    assert set(added.split()) <= {"#", "hyprconf", "overlay", "include", "hyprconf.conf"}


def test_hyprconf_kitty_include_file_is_self_contained(tmp_path: Path) -> None:
    """It must not restate anything Omarchy's kitty.conf owns."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    body = _code_only((env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "background_opacity 0.85" in body
    assert "cursor_trail" in body
    for owned in ("font_family", "font_size", "listen_on", "allow_remote_control", "include "):
        assert owned not in body, owned


def test_shell_line_points_at_zsh_only_when_zsh_exists(tmp_path: Path) -> None:
    """Writing `shell /bin/zsh` without zsh present would stop kitty starting."""
    env = _setup(tmp_path)
    # _HYPRCONF_ZSH="" is the seam for "no zsh on this box" — the real lookup
    # would otherwise find the host's zsh, since /usr/bin has to stay on PATH
    # for coreutils.
    assert _run(env, "--no-update", zsh="").returncode == 0
    body = _code_only((env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "shell " not in body

    env2 = _setup(tmp_path / "with-zsh")
    _run(env2, "--no-update")
    body2 = _code_only((env2["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "shell " in body2


def test_theme_is_installed_as_a_symlink(tmp_path: Path) -> None:
    """omarchy-theme-set only takes its permissive path for a symlinked theme.

    Its check is `[[ ! -L $source && -d $source/.git ]]` — a real directory
    inside a git checkout would be treated as a stranger's theme and filtered
    through INSTALLED_THEME_DENIED instead.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert (env["home"] / ".config" / "omarchy" / "themes" / "hyprconf").is_symlink()


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_no_update_never_runs_omarchy_update(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-update") for c in _calls(env))


def test_sync_runs_omarchy_update_and_never_pacman(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--sync")
    calls = _calls(env)
    assert any(c.startswith("omarchy-update") for c in calls)
    assert not any(c.startswith("pacman") for c in calls)


def test_no_packages_skips_the_only_privileged_stage(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--no-packages", "--no-update")
    assert not any(c.startswith("omarchy-pkg-add") for c in _calls(env))

    env2 = _setup(tmp_path / "default-run")
    _run(env2, "--no-update")
    assert any(c.startswith("omarchy-pkg-add") for c in _calls(env2))


def test_unknown_flag_is_rejected(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    proc = _run(env, "--definitely-not-a-flag")
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# The post-update hook
# ---------------------------------------------------------------------------


def test_hook_is_installed_with_a_resolved_path(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--no-update")
    installed = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    body = installed.read_text()
    assert "@HYPRCONF_DIR@" not in body, "placeholder was not substituted"
    assert str(REPO_ROOT) in body
    assert os.access(installed, os.X_OK)


def test_hook_cannot_recurse_or_escalate() -> None:
    """It runs *inside* omarchy-update, so it must not update or use sudo."""
    code = _code_only(HOOK.read_text())
    assert "--no-update" in code and "--no-packages" in code
    # It must not re-enter the thing that invoked it, nor the wrapper for it.
    assert "omarchy-update" not in code
    assert "hyprsync" not in code
    assert "HYPRCONF_SYNC_RUNNING" in code, "missing the hyprsync recursion guard"
    assert "sudo" not in code
    # No `set -e`: omarchy-hook must never let a hook abort an update.
    assert "set -e" not in code


# ---------------------------------------------------------------------------
# Static scans over the whole overlay tree
# ---------------------------------------------------------------------------


def _overlay_scripts() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "omarchy"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [REPO_ROOT / line for line in out.stdout.split()]
    return [p for p in paths if p.suffix in {".sh", ""} and p.is_file() and p.suffix != ".png"]


def test_overlay_never_uses_forbidden_pacman_forms() -> None:
    """`-Syu` is blocked by Omarchy's ALPM guard; `-R` would dismantle Omarchy."""
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        assert "pacman -Syu" not in code, script
        assert "pacman -Syyu" not in code, script
        assert "pacman -R" not in code, script


def test_overlay_never_reaches_into_the_standalone_installer() -> None:
    """setup.sh's remove_aur_packages would offer to uninstall Omarchy itself."""
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        assert "setup.sh" not in code, script
        assert "remove_aur_packages" not in code, script


def test_overlay_installs_no_aur_packages() -> None:
    """Per AGENTS.md: official repos only, and AUR never without asking first."""
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        assert "yay " not in code, script
        assert "makepkg" not in code, script
        assert "omarchy-pkg-aur-add" not in code, script
