"""install.sh — the overlay installer for Omarchy systems.

This installer is unusual for hyprconf in that it runs on a machine it does not
own: Omarchy owns the base system, and the overlay's whole design constraint is
to disturb it as little as possible. Most of what is asserted here is therefore
*restraint* — what the installer must NOT do:

  * never `chsh` (the login shell stays bash, so Omarchy's rc chain, aliases,
    completions, session and scripts keep working)
  * never rewrite Omarchy's ~/.config/kitty/kitty.conf beyond appending one
    `include` line (it owns the theme include, listen_on, font_family/font_size)
  * never point `omarchy-default-terminal` at a kitty that is not installed —
    it checks nothing (Omarchy 4.0.0-1 writes ~/.config/xdg-terminals.list and
    notifies), so SUPER+RETURN and every TUI launcher would have no terminal
  * never `pacman -Syu` (an Omarchy ALPM AbortOnFail hook blocks it) or
    `pacman -R` (it would dismantle Omarchy) — the one removal, Code - OSS
    before Omarchy's own VS Code installer, goes through omarchy-pkg-drop
  * never switch the active theme — hyprconf's theme is installed into the
    theme menu, and which one is active stays the user's choice

Everything runs against fake `omarchy-*` binaries in a throwaway HOME, so the
suite is hermetic in a bare archlinux container per the testing rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
HOOK = REPO_ROOT / "hooks" / "post-update.d" / "10-hyprconf"
PROTONVPN_INSTALLER = REPO_ROOT / "bin" / "hyprconf-install-service-protonvpn"
VULKAN_GPU = REPO_ROOT / "bin" / "hyprconf-vulkan-gpu"
MONITOR_PRESET = REPO_ROOT / "bin" / "hyprconf-monitor-preset"
GAPS = REPO_ROOT / "bin" / "hyprconf-gaps"
# Omarchy's own validator for a plugin folder (pure: reads the manifest and
# the tree, touches nothing); real when installed, the test skips otherwise.
PLUGIN_VALIDATE = Path("/usr/share/omarchy/bin/omarchy-plugin-validate")

# Where hyprconf-monitor-preset puts the chosen preset: Omarchy's Hyprland
# toggles directory, loaded after ~/.config/hypr/monitors.lua.
TOGGLE = Path(".local") / "state" / "omarchy" / "toggles" / "hypr" / "hyprconf-monitor-preset.lua"

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

# Omarchy's config/omarchy/extensions/omarchy-menu.jsonc (4.0.0-1), verbatim:
# all comments, the shape a fresh box's user extension file has.
OMARCHY_MENU_EXTENSION = r"""{
  // Extend the Quickshell Omarchy menu with JSONC.
  //
  // IDs are object keys. The parent is inferred from the dotted id, so
  // "personal.notes" appears under "personal", and "personal" appears on the
  // root menu. Reuse an existing id to override/extend it.
  //
  // Fields:
  //   icon        Nerd Font glyph shown in the icon column.
  //   label       Visible row title.
  //   action      Shell command to run. If omitted, the row is a submenu.
  //   target      Existing submenu id to open. Use for links/aliases.
  //   provider    Runtime provider function/command returning JSON rows.
  //   aliases     alternate `omarchy menu summon <name>` routes; also searchable.
  //   description Optional subtitle and extra search text.
  //   when        Shell condition; hide row when it fails.
  //   checked     Shell condition; append ✓ when it succeeds.
  //
  // Examples:
  // "personal": {"icon":"","label":"Personal"},
  // "personal.notes": {"icon":"󰎞","label":"Notes","action":"omarchy-launch-editor ~/notes"},
  // "personal.files": {"icon":"","label":"Files","action":"uwsm-app -- nautilus ~/Documents"},
  //
  // Only use provider when a provider_name function or command named "name"
  // returns JSON rows. Static submenus only need dotted ids.
  //
  // Example: replace the default About action by reusing the same id. Existing
  // fields are kept unless overridden.
  // "about": {"icon":"","label":"About","action":"omarchy-launch-or-focus-tui \"zsh -c 'fastfetch; read -k 1'\""},
}
"""


# Omarchy's default/firefox/policies.json as omarchy-install-browser copies
# it (4.0.0-1: Preferences only), with one pref hyprconf's policy also sets —
# the merge must keep Omarchy's others and let ours win on that one.
OMARCHY_FIREFOX_POLICY = {
    "policies": {
        "Preferences": {
            "media.ffmpeg.vaapi.enabled": {"Value": True, "Status": "default"},
            "widget.wayland.fractional-scale.enabled": {"Value": True, "Status": "default"},
            "browser.compactmode.show": {"Value": False, "Status": "default"},
        }
    }
}

# omarchy-hook-install <type> <file> (4.0.0-1): mkdir -p the .d dir, cp under
# the file's basename, chmod 755 — reproduced so later stages find the hook.
HOOK_INSTALL = (
    'd="$HOME/.config/omarchy/hooks/$1.d"; mkdir -p "$d"; cp "$2" "$d/${2##*/}"; '
    'chmod 755 "$d/${2##*/}"'
)

# omarchy-theme-refresh re-sets the current theme, which renders every user
# template (~/.config/omarchy/themed/*.tpl) into the current theme dir from
# its colors.toml (omarchy-theme-set-templates); the fake does that part.
THEME_REFRESH = """\
t="$HOME/.local/state/omarchy/current/theme"; [ -f "$t/colors.toml" ] || exit 0
s=""
while IFS= read -r l; do k="${l%% *}"; v="${l#*\\"}"; v="${v%\\"*}"; s="$s;s|{{ $k }}|$v|g"; done \\
  < <(grep -E '^[a-z_]+ = "' "$t/colors.toml")
for f in "$HOME"/.config/omarchy/themed/*.tpl; do
  [ -f "$f" ] || continue; n="${f##*/}"; sed "${s#;}" "$f" > "$t/${n%.tpl}"
done"""

# Every monitor preset the overlay ships. Each carries the workspace-to-monitor
# rules for its layout, so they travel as whole files.
PRESETS = (
    "pcMonitors.bedroom.lua",
    "pcMonitors.kitchen.lua",
    "pcMonitors.K.lua",
    "pcMonitors.lua",
    "laptopMonitors.lua",
)


def _stub(path: Path, calls: Path, body: str = "exit 0") -> None:
    path.write_text(STUB.format(calls=calls, body=body))
    path.chmod(0o755)


# A GPU for _sysfs: (PCI address, vendor, device, connected outputs). The
# harness default is one GPU driving two displays — nothing for the Vulkan
# check to do, so no other test is touched by it.
SINGLE_GPU = (("0000:01:00.0", "0x1002", "0x744c", 2),)


def _sysfs(env: dict, gpus: tuple[tuple[str, str, str, int], ...]) -> None:
    """A fake /sys/bus/pci/devices + /sys/class/drm for hyprconf-vulkan-gpu,
    replacing the harness default. Per GPU: class 0x030000 and the id files
    under its PCI dir, card<N>/device linking back to that dir, and one
    card<N>-DP-<M>/status per connector — the real tree's shape (cards and
    connectors numbered from 1, Linux 7.1) — beside one non-display device
    the class filter must skip."""
    pci, drm = env["sys_pci"], env["sys_drm"]
    for tree in (pci, drm):
        shutil.rmtree(tree, ignore_errors=True)
        tree.mkdir(parents=True)
    bridge = pci / "0000:00:00.0"
    bridge.mkdir()
    (bridge / "class").write_text("0x060000\n")
    (bridge / "vendor").write_text("0x1022\n")
    (bridge / "device").write_text("0x14d8\n")
    connector = 0
    for n, (addr, vendor, device, connected) in enumerate(gpus, 1):
        dev = pci / addr
        dev.mkdir()
        (dev / "class").write_text("0x030000\n")
        (dev / "vendor").write_text(f"{vendor}\n")
        (dev / "device").write_text(f"{device}\n")
        card = drm / f"card{n}"
        card.mkdir()
        (card / "device").symlink_to(dev)
        for i in range(2):
            connector += 1
            status = drm / f"card{n}-DP-{connector}" / "status"
            status.parent.mkdir()
            status.write_text("connected\n" if i < connected else "disconnected\n")


def _terminal_stub(tmp_path: Path, set_status: int = 0) -> str:
    """omarchy-default-terminal: reports foot until something sets it, then
    what was set. The set form writes first and exits `set_status` — the real
    one's status is its closing notification's (no set -e, 4.0.0-1)."""
    return (
        f'if [ $# -eq 0 ]; then cat "{tmp_path}/term" 2>/dev/null || echo foot;'
        f' else printf "%s" "$1" > "{tmp_path}/term"; exit {set_status}; fi'
    )


def _setup(
    tmp_path: Path, *, with_omarchy: bool = True, with_zsh: bool = True, with_kitty: bool = True
) -> dict:
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
        "omarchy-font-set",
        "omarchy-default-browser",
        "omarchy-default-editor",
        "omarchy-shell",
        "omarchy-plugin-enable",
        "omarchy-plugin-disable",
        "omarchy-plugin-remove",
        "omarchy-plugin-catalog",
        "omarchy-restart-shell",
        "omarchy-bar",
        "omarchy-update",
        # Firefox and VS Code go in through Omarchy's own installers; the
        # Code - OSS conflict is cleared with Omarchy's own remover.
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
        "omarchy-pkg-drop",
        "sudo",
        "hyprctl",
        # hyprconf-monitor-preset (run by several tests here) reports through these;
        # the real ones would put a notification and an OSD on the developer's
        # desktop every time the suite runs.
        "omarchy-notification-send",
        "omarchy-osd",
        # Asserted never to run: switching the login shell, and pacman
        # directly (the container has a real one; a call must be seen, not
        # reach it).
        "chsh",
        "pacman",
        # hyprconf-vulkan-gpu's prompt; the real one takes over the terminal.
        "gum",
    ):
        _stub(bins / name, calls)
    # Named so a "no Omarchy here" run can point the installer at a command
    # that really is absent — /usr/bin/omarchy-pkg-add exists on the machines
    # this overlay is developed on, so simply not stubbing it proves nothing.
    pkg_add = "omarchy-pkg-add" if with_omarchy else "omarchy-pkg-add-absent"
    if with_omarchy:
        _stub(bins / pkg_add, calls)
    # Same for kitty: /usr/bin has to stay on PATH for coreutils, and the
    # host's own kitty would answer the "is it installed" check.
    kitty = "kitty" if with_kitty else "kitty-absent"
    if with_kitty:
        _stub(bins / kitty, calls)
    if with_zsh:
        _stub(bins / "zsh", calls)
    # No plugin is enabled yet, so the jq guard must fall through to enable.
    _stub(bins / "omarchy-plugin-list", calls, 'echo "[]"')
    _stub(bins / "jq", calls, "exit 1")
    # Omarchy's package probe (pacman -Q per name): everything present unless
    # a test says otherwise, so the steady-state box is the default and each
    # install flow is opted into.
    _stub(bins / "omarchy-pkg-present", calls)
    _stub(bins / "omarchy-hook-install", calls, HOOK_INSTALL)
    _stub(bins / "omarchy-theme-refresh", calls, THEME_REFRESH)
    # fc-list is how the installer discovers whether the font it wants is really
    # present; the real one on the test host would answer for the host's fonts.
    _stub(bins / "fc-list", calls, 'echo "GeistMono Nerd Font,GeistMono NF"')
    _stub(bins / "omarchy-default-terminal", calls, _terminal_stub(tmp_path))
    # `clone` must materialise a directory; everything else is a no-op.
    _stub(bins / "git", calls, 'if [ "$1" = clone ]; then mkdir -p "${@: -1}"; fi; exit 0')

    # Seed the parts of a fresh Omarchy $HOME the installer interacts with.
    (home / ".config" / "kitty").mkdir(parents=True)
    (home / ".config" / "kitty" / "kitty.conf").write_text(OMARCHY_KITTY_CONF)
    (home / ".config" / "hypr").mkdir(parents=True)
    for stock in ("bindings.lua", "input.lua", "looknfeel.lua"):
        (home / ".config" / "hypr" / stock).write_text(f"-- stock omarchy {stock}\n")
    (omarchy_path / "default" / "bash").mkdir(parents=True)
    # Omarchy's shipped shell.json defaults — what stage_idle starts from
    # when the user has no shell.json yet.
    (omarchy_path / "config" / "omarchy").mkdir(parents=True)
    (omarchy_path / "config" / "omarchy" / "shell.json").write_text(
        json.dumps({"version": 1, "idle": {"lock": 300, "screensaver": 150}})
    )
    # Omarchy's template for the user's menu extension file — what stage_menu
    # seeds ~/.config/omarchy/extensions/omarchy-menu.jsonc from.
    (omarchy_path / "config" / "omarchy" / "extensions").mkdir()
    (omarchy_path / "config" / "omarchy" / "extensions" / "omarchy-menu.jsonc").write_text(
        OMARCHY_MENU_EXTENSION
    )
    # Omarchy's Firefox prefs — what stage_firefox merges under hyprconf's.
    (omarchy_path / "default" / "firefox").mkdir(parents=True)
    (omarchy_path / "default" / "firefox" / "policies.json").write_text(
        json.dumps(OMARCHY_FIREFOX_POLICY, indent=2) + "\n"
    )

    env = {
        "home": home,
        "bins": bins,
        "omarchy_path": omarchy_path,
        "calls": calls,
        "pkg_add": pkg_add,
        "kitty": kitty,
        "sys_pci": tmp_path / "sys" / "pci",
        "sys_drm": tmp_path / "sys" / "drm",
    }
    _sysfs(env, SINGLE_GPU)
    return env


def _run(
    env: dict,
    *args: str,
    zsh: str | None = None,
    zsh_bin: str | None = None,
    extra_env: dict[str, str] | None = None,
    install_sh: Path = INSTALL_SH,
) -> subprocess.CompletedProcess:
    """Run install.sh against the fake tree. Returns the completed process.

    `zsh` pins the resolved zsh path outright; `zsh_bin` instead renames the
    binary the installer looks up on PATH, which is how a test can model "zsh
    does not exist until the package stage installs it" on a host whose own
    /usr/bin/zsh would otherwise always be found. `install_sh` runs a copy of
    the installer (see _checkout) instead of the one in this checkout.
    """
    child_env = {
        **_child_env(env),
        "OMARCHY_PATH": str(env["omarchy_path"]),
        "_HYPRCONF_PKG_ADD": env["pkg_add"],
        "_HYPRCONF_KITTY_BIN": env["kitty"],
        # The plugin-discovery and shell.json waits poll stubs that never
        # answer (a test modelling the shell's writes raises it again).
        "_HYPRCONF_PLUGIN_WAIT": "0",
        # hyprconf-vulkan-gpu reads sysfs: the fake tree (_sysfs), never the
        # host's, and no vulkaninfo — the host's would answer for its GPUs.
        "_HYPRCONF_SYS_PCI": str(env["sys_pci"]),
        "_HYPRCONF_SYS_DRM": str(env["sys_drm"]),
        "_HYPRCONF_VULKANINFO": "vulkaninfo-absent",
    }
    if zsh is not None:
        child_env["_HYPRCONF_ZSH"] = zsh
    if zsh_bin is not None:
        child_env["_HYPRCONF_ZSH_BIN"] = zsh_bin
    if extra_env:
        child_env.update(extra_env)
    return subprocess.run(
        ["bash", str(install_sh), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=child_env,
    )


# The payload install.sh reads at run time — enough of the repo to run every
# stage from a copy. lib/ is only reached through the theme-set hook's
# PYTHONPATH, which points at the real checkout, so it is not needed here.
PAYLOAD = (
    "install.sh",
    "packages",
    "hypr",
    "bin",
    "hooks",
    "zsh",
    "kitty",
    "fastfetch",
    "themes",
    "wallpapers",
    "plugins",
    "infra",
    "themed",
)

# A git that is real for everything the refresh guard needs (`checkout --`)
# and still fake for the two things a hermetic run must never do: clone Oh My
# Zsh / powerlevel10k off the network, and pull.
GIT_PASSTHROUGH = """\
if [ "$1" = clone ]; then mkdir -p "${@: -1}"; exit 0; fi
case " $* " in *" pull "*) exit 0 ;; esac
exec "$(PATH=/usr/bin:/bin command -v git)" "$@"
"""


def _checkout(tmp_path: Path) -> Path:
    """A throwaway git checkout of the overlay payload.

    The refresh-guard tests have to simulate `omarchy refresh` clobbering the
    checkout and the installer repairing it with git — which must never be
    rehearsed on the real repository the suite runs from.
    """
    repo = tmp_path / "checkout"
    repo.mkdir()
    for name in PAYLOAD:
        src = REPO_ROOT / name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, repo / name)
    git = ["git", "-c", "user.name=hyprconf-tests", "-c", "user.email=tests@example.invalid"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True, timeout=30)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True, timeout=30)
    subprocess.run([*git, "commit", "-qm", "payload"], cwd=repo, check=True, timeout=30)
    return repo


def _child_env(env: dict) -> dict[str, str]:
    """The pinned environment of everything run against the fake tree: the
    fakes first, then only /usr/bin and /bin (never the host's PATH)."""
    return {"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"}


def _real_jq(env: dict) -> None:
    """The real jq behind the recording stub — the default stub plays
    "broken" — for the stages that read or rewrite JSON; skips without one."""
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq available")
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')


def _switch(env: dict, *args: str) -> subprocess.CompletedProcess:
    """hyprconf-monitor-preset as stage_bin installed it, against the fakes."""
    tool = env["home"] / ".local" / "bin" / "hyprconf-monitor-preset"
    return subprocess.run(
        ["bash", str(tool), *args],
        capture_output=True,
        text=True,
        env=_child_env(env),
        timeout=30,
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


def _code_only_qml(body: str) -> str:
    """Drop // comment lines, so a scan cannot match the prose explaining it."""
    return "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("//"))


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
    for script in (INSTALL_SH, HOOK, PROTONVPN_INSTALLER, VULKAN_GPU, MONITOR_PRESET, GAPS):
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


def test_default_terminal_is_never_set_to_an_absent_kitty(tmp_path: Path) -> None:
    """omarchy-default-terminal (4.0.0-1) checks nothing: it writes the desktop
    id into ~/.config/xdg-terminals.list and notifies. Pointing it at a kitty
    that is not installed would leave SUPER+RETURN and every TUI launcher
    with no terminal, so the stage stops first — and never calls the setter
    (an argument is what makes it write)."""
    env = _setup(tmp_path, with_kitty=False)
    proc = _run(env, "--no-update")
    assert proc.returncode != 0
    assert "kitty" in proc.stderr
    assert not any(c.startswith("omarchy-default-terminal ") for c in _calls(env)), (
        "omarchy-default-terminal was called with an argument"
    )
    assert not (env["home"] / ".config" / "xdg-terminals.list").exists()


def test_a_failed_terminal_setter_does_not_take_the_install_down(tmp_path: Path) -> None:
    """omarchy-default-terminal (4.0.0-1) has no set -e and exits with its
    closing omarchy-notification-send's status, which fails with no shell to
    notify (a TTY first run) — after ~/.config/xdg-terminals.list is written.
    Every later stage must still run, and the re-run finds kitty current."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-default-terminal", env["calls"], _terminal_stub(tmp_path, 1))
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-default-terminal kitty" in _calls(env)
    assert (env["home"] / ".zshrc").exists()  # a stage well after the terminal one
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert "omarchy-default-terminal kitty" not in _calls(env)


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


def test_zsh_installed_by_the_package_stage_is_used_in_the_same_run(tmp_path: Path) -> None:
    """The zsh lookup must happen AFTER packages, not when the script starts.

    On a fresh Omarchy zsh does not exist until stage_packages installs it. A
    lookup at startup pins the empty string for the whole run, and the machine
    comes out of its first install with no ~/.zshrc, no powerlevel10k and bash
    in kitty — which is exactly what happened on the first real install.
    """
    env = _setup(tmp_path, with_zsh=False)
    zsh = env["bins"] / "zsh-installed-by-pkg-add"
    # Stand in for `pacman -S zsh`: the binary appears while the run is going.
    _stub(
        env["bins"] / env["pkg_add"],
        env["calls"],
        f'printf "#!/usr/bin/env bash\\nexit 0\\n" > "{zsh}"; chmod 755 "{zsh}"',
    )

    proc = _run(env, "--no-update", zsh_bin=zsh.name)
    assert proc.returncode == 0, proc.stderr

    assert (env["home"] / ".zshrc").read_text().count("powerlevel10k") >= 1
    assert (env["home"] / ".p10k.zsh").is_symlink()
    assert (env["home"] / ".oh-my-zsh").is_dir()
    kitty_conf = (env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text()
    assert f"shell {zsh}" in kitty_conf


# ---------------------------------------------------------------------------
# The ~/.config/hypr override files
# ---------------------------------------------------------------------------


def test_hypr_overrides_are_symlinked_with_a_stock_backup(tmp_path: Path) -> None:
    """bindings/input/looknfeel are Omarchy's own post-defaults require points.

    Each stock file is Omarchy's commented template, so the backup is what
    makes the overlay reversible by hand.
    """
    env = _setup(tmp_path)
    for _ in range(2):  # the backup must not be re-taken from our own symlink
        _run(env, "--no-update")
    hypr = env["home"] / ".config" / "hypr"
    for name in ("bindings.lua", "input.lua", "looknfeel.lua"):
        assert hypr.joinpath(name).is_symlink(), name
        assert hypr.joinpath(name).resolve() == REPO_ROOT / "hypr" / name
        assert hypr.joinpath(f"{name}.stock").read_text() == f"-- stock omarchy {name}\n"


def test_monitor_presets_are_installed_without_touching_the_active_layout(
    tmp_path: Path,
) -> None:
    """Presets are inert files; monitors.lua stays whatever the machine chose.

    Omarchy writes its own auto layout there, and the overlay never replaces
    it: a chosen preset goes into Omarchy's Hyprland toggles directory, which
    hyprland.lua requires AFTER monitors.lua (config/hypr/hyprland.lua:19,26,
    4.0.0-1), so no backup of monitors.lua is needed or taken.
    """
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")
    for preset in PRESETS:
        assert hypr.joinpath(preset).is_file(), preset
    assert hypr.joinpath("monitors.lua").read_text() == "-- omarchy auto layout\n"
    assert not hypr.joinpath("monitors.lua.stock").exists()
    assert not (env["home"] / TOGGLE).exists()


def test_monitor_preset_reaches_every_preset_and_back(tmp_path: Path) -> None:
    """Each shipped preset must be selectable, and stock must give the layout
    back to Omarchy's monitors.lua alone. The presets carry hyprconf's
    workspace-to-monitor rules, so one that cannot be named is dead config.
    A COPY of the preset lands in the toggles file — never a link, and
    monitors.lua is never touched — the mechanism Omarchy's own
    omarchy-hyprland-monitor-internal uses for its hl.monitor line.
    """
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")
    toggle = env["home"] / TOGGLE

    for name, preset in (
        ("bedroom", "pcMonitors.bedroom.lua"),
        ("kitchen", "pcMonitors.kitchen.lua"),
        ("K", "pcMonitors.K.lua"),
        ("pc", "pcMonitors.lua"),
        ("laptop", "laptopMonitors.lua"),
    ):
        proc = _switch(env, name)
        assert proc.returncode == 0, proc.stderr
        assert toggle.is_file() and not toggle.is_symlink(), name
        assert toggle.read_bytes() == hypr.joinpath(preset).read_bytes(), name
        assert not hypr.joinpath("monitors.lua").is_symlink()
        assert hypr.joinpath("monitors.lua").read_text() == "-- omarchy auto layout\n"

    proc = _switch(env, "stock")
    assert proc.returncode == 0, proc.stderr
    assert not toggle.exists()
    assert hypr.joinpath("monitors.lua").read_text() == "-- omarchy auto layout\n"


def test_natural_scroll_is_the_default(tmp_path: Path) -> None:
    """Omarchy ships natural_scroll off for the touchpad and off for the mouse."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    body = (env["home"] / ".config" / "hypr" / "input.lua").read_text()
    # Once for the pointer, once inside the touchpad table.
    assert body.count("natural_scroll = true") == 2


def test_hypr_overrides_parse_as_lua(tmp_path: Path) -> None:
    """A syntax error here is a broken desktop, not a failed test run."""
    luac = shutil.which("luac") or shutil.which("luac5.4")
    if luac is None:
        pytest.skip("no luac available to parse the Hyprland Lua config")
    for lua in sorted((REPO_ROOT / "hypr").glob("*.lua")):
        proc = subprocess.run(
            [luac, "-p", str(lua)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr


def test_theme_is_installed_as_a_symlink(tmp_path: Path) -> None:
    """A symlink, so a `git pull` updates the theme in place; omarchy-theme-set
    (4.0.0-1) only tests `-d` and `cp -r`s the contents, both of which follow
    a link."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    link = env["home"] / ".config" / "omarchy" / "themes" / "dracula"
    assert link.is_symlink() and link.resolve() == REPO_ROOT / "themes" / "dracula"


def test_never_switches_the_active_theme(tmp_path: Path) -> None:
    """Installing lists hyprconf's theme; it never takes the active one away.

    The overlay re-applies itself after every Omarchy update, so a stage that
    activated the theme would keep overriding a choice the user had since made.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert "omarchy-theme-set" not in _commands(env)
    # With any other theme active — Omarchy's own, say — nothing is switched.
    active = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme.name"
    active.parent.mkdir(parents=True)
    active.write_text("tokyo-night\n")
    _run(env, "--no-update")
    assert "omarchy-theme-set" not in _commands(env)


def test_a_user_installed_theme_directory_is_left_alone(tmp_path: Path) -> None:
    """A real ~/.config/omarchy/themes/dracula (one the user installed with
    `omarchy theme install`) is theirs: `ln -sfn` over a directory would
    only drop a stray link inside it, so the stage leaves it untouched and
    says so."""
    env = _setup(tmp_path)
    theme = env["home"] / ".config" / "omarchy" / "themes" / "dracula"
    theme.mkdir(parents=True)
    (theme / "colors.toml").write_text("theirs\n")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not theme.is_symlink()
    assert sorted(p.name for p in theme.iterdir()) == ["colors.toml"]
    assert "dracula" in proc.stderr


def test_screensaver_timeout_is_set_once(tmp_path: Path) -> None:
    """idle.screensaver becomes 900 s (15 min) from Omarchy's 150 s, seeded
    from the shipped defaults when the user has no shell.json yet; every
    other key survives, the lock timeout is left alone, the shell reloads
    its config, and a later user value is never taken back."""
    env = _setup(tmp_path)
    _real_jq(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    data = json.loads(shell_json.read_text())
    assert data["idle"] == {"lock": 300, "screensaver": 900}
    assert data["version"] == 1
    assert "omarchy-shell shell reloadConfig" in _calls(env)
    assert (env["home"] / ".local" / "state" / "hyprconf" / "idle-applied").exists()

    data["idle"]["screensaver"] = 600  # the user's later choice
    shell_json.write_text(json.dumps(data))
    _run(env, "--no-update")
    assert json.loads(shell_json.read_text())["idle"]["screensaver"] == 600


def test_firefox_theme_tool_is_installed_with_the_checkout_path(tmp_path: Path) -> None:
    """bin/hyprconf-firefox-theme is a launcher for lib/hyprconf/firefox_theme.py;
    it needs the checkout on PYTHONPATH, so stage_bin substitutes
    @HYPRCONF_DIR@ the way the hooks get it. Its --status must run from the
    installed copy."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    tool = env["home"] / ".local" / "bin" / "hyprconf-firefox-theme"
    proc = subprocess.run(
        [str(tool), "--status"], capture_output=True, text=True, timeout=60, env=_child_env(env)
    )
    assert proc.returncode == 0, proc.stderr
    assert "userChrome.css" in proc.stdout


def test_omarchys_own_edits_to_monitors_lua_survive_a_preset_switch(tmp_path: Path) -> None:
    """Omarchy keeps writing to monitors.lua after the overlay is installed —
    omarchy-hyprland-monitor-scaling seds the scale lines in place. A preset
    switch never replaces that file, so nothing Omarchy wrote is lost, and
    `stock` is just the toggle going away."""
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")

    # Omarchy edits the live file after install, exactly as its scaling tool does.
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n-- DRIFTED\n")

    assert _switch(env, "bedroom").returncode == 0
    assert "DRIFTED" in hypr.joinpath("monitors.lua").read_text()
    assert _switch(env, "stock").returncode == 0
    assert "DRIFTED" in hypr.joinpath("monitors.lua").read_text()


@pytest.mark.parametrize("restore_from", ["stock", "template"])
def test_monitors_lua_symlink_from_an_earlier_release_is_migrated_once(
    tmp_path: Path, restore_from: str
) -> None:
    """v4.0.0–v4.2.0's switch_monitor.sh saved Omarchy's monitors.lua as
    monitors.lua.stock and symlinked the chosen preset over it. The upgrade
    carries that over once: the link's target becomes the toggles file (so
    the desk keeps its layout) and monitors.lua is a real file again — from
    the .stock copy, else Omarchy's template — with the .stock left in place."""
    env = _setup(tmp_path)
    templates = _stock_templates(env)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("pcMonitors.bedroom.lua").write_text("-- my desk, my monitors\n")
    hypr.joinpath("monitors.lua").symlink_to(hypr / "pcMonitors.bedroom.lua")
    if restore_from == "stock":
        hypr.joinpath("monitors.lua.stock").write_text("-- omarchy auto layout\n")
        expected = "-- omarchy auto layout\n"
    else:
        expected = (templates / "monitors.lua").read_text()

    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "pcMonitors.bedroom.lua" in proc.stdout and "monitors.lua" in proc.stdout
    assert (env["home"] / TOGGLE).read_text() == "-- my desk, my monitors\n"
    monitors = hypr / "monitors.lua"
    assert not monitors.is_symlink() and monitors.read_text() == expected
    assert hypr.joinpath("pcMonitors.bedroom.lua").read_text() == "-- my desk, my monitors\n"
    if restore_from == "stock":
        assert hypr.joinpath("monitors.lua.stock").exists()

    before = _tree_hash(env["home"])
    proc = _run(env, "--no-update")
    assert "was a link" not in proc.stdout
    assert _tree_hash(env["home"]) == before


def test_dangling_monitors_lua_symlink_is_restored_without_a_toggle(tmp_path: Path) -> None:
    """The link's preset is gone (deleted by hand): nothing to carry over, so
    no toggle file is written, monitors.lua still comes back as a real file,
    and the message says the layout is Omarchy's now — never that the preset
    survived as the toggles file."""
    env = _setup(tmp_path)
    _stock_templates(env)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").symlink_to(hypr / "pcMonitors.gone.lua")
    hypr.joinpath("monitors.lua.stock").write_text("-- omarchy auto layout\n")

    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (env["home"] / TOGGLE).exists()
    monitors = hypr / "monitors.lua"
    assert not monitors.is_symlink() and monitors.read_text() == "-- omarchy auto layout\n"
    assert "toggles file now" not in proc.stdout
    assert "pcMonitors.gone.lua, which is gone" in proc.stderr
    assert "hyprconf-monitor-preset <name>" in proc.stderr


def test_presets_are_seeded_once_and_never_overwritten(tmp_path: Path) -> None:
    """A preset describes one machine's desk, so the machine owns it after seeding.

    The post-update hook re-runs the installer after every Omarchy update, and
    switch_monitor.sh promises edits survive re-selecting a preset — copying the
    repo's version over the top on each run would break that silently.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    preset = env["home"] / ".config" / "hypr" / "pcMonitors.bedroom.lua"
    preset.write_text("-- my desk, my monitors\n")
    _run(env, "--no-update")
    assert preset.read_text() == "-- my desk, my monitors\n"


def test_no_shipped_script_uses_the_dead_hyprctl_keyword_path() -> None:
    """`hyprctl keyword` is a silent no-op under Hyprland's Lua parser.

    It answers "keyword can't work with non-legacy parsers. Use eval." and
    still exits 0 — so a script using it fails without failing, and the hotkey
    driving it simply does nothing. `hyprctl eval` is the replacement and does
    report errors (exit 7). Verified against Hyprland 0.56.2.
    """
    offenders = []
    for script in sorted((REPO_ROOT / "bin").glob("hyprconf-*")):
        for lineno, line in enumerate(_code_only(script.read_text()).splitlines(), 1):
            if re.search(r"hyprctl\s+(--batch\s+)?[\"']?keyword\b", line):
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert not offenders, "hyprctl keyword is a silent no-op — use hyprctl eval:\n" + "\n".join(
        offenders
    )


def test_osd_keys_are_left_to_omarchy(tmp_path: Path) -> None:
    """Volume and brightness keys must keep reaching Omarchy's own commands.

    hyprconf bound them to raw wpctl / hyprconf-brightness, whose extra job was
    feeding hyprconf's quickshell OSD. That OSD does not exist here, and
    Omarchy's own commands end by calling omarchy-osd — so rebinding these keys
    silently removes the on-screen indicator while still changing the level,
    which reads as "the volume popup disappeared".
    """
    # Match on bind CALLS, not on the file's prose: the comments explaining why
    # these keys are left alone necessarily name them.
    bindings = "\n".join(
        line
        for line in (REPO_ROOT / "hypr" / "bindings.lua").read_text().splitlines()
        if not line.lstrip().startswith("--")
    )
    for key in (
        "XF86AudioRaiseVolume",
        "XF86AudioLowerVolume",
        "XF86AudioMute",
        "XF86AudioMicMute",
        "XF86MonBrightnessUp",
        "XF86MonBrightnessDown",
        "XF86AudioNext",
        "XF86AudioPrev",
        "XF86AudioPlay",
        "XF86AudioPause",
    ):
        assert key not in bindings, f"{key} must be left to Omarchy (it drives the OSD)"


def test_every_binding_carries_a_description(tmp_path: Path) -> None:
    """A description is what puts a key in Omarchy's SUPER+K keybindings menu.

    hl.bind records none, so hyprconf's whole keymap was invisible there while
    the menu still listed the Omarchy defaults hyprconf had replaced — worse
    than listing nothing. o.bind (via the rebind helper) records one.
    """
    src = (REPO_ROOT / "hypr" / "bindings.lua").read_text()
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("--")]
    assert not [ln for ln in code if re.search(r"\bhl\.bind\s*\(", ln)], (
        "use rebind()/o.bind so the key appears in the keybindings menu"
    )
    # rebind(keys, description, dispatcher[, options]) — the description is a
    # literal string, so a two-argument call is a dropped description.
    for ln in code:
        if ln.lstrip().startswith("local function rebind"):
            continue  # the helper's own signature, not a call
        m = re.search(r"\brebind\((.*)\)\s*$", ln)
        if m:
            assert '"' in m.group(1).split(",", 1)[-1], f"missing description: {ln.strip()}"


def test_no_shipped_script_uses_the_dead_two_token_dispatch() -> None:
    """`hyprctl dispatch dpms on` is a 0.55-ism that no longer parses.

    Under Hyprland's Lua parser the two-token form is a syntax error and exits
    non-zero into a discarded stream, so the dark-output recovery in the
    monitor-preset tool never ran once. The working form is the one Omarchy
    uses: hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'.
    """
    offenders = []
    for script in sorted((REPO_ROOT / "bin").glob("hyprconf-*")):
        for lineno, line in enumerate(_code_only(script.read_text()).splitlines(), 1):
            if re.search(r"hyprctl\s+dispatch\s+[a-z_]+\s+[a-z_]+", line):
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "two-token `hyprctl dispatch` does not parse under the Lua config — "
        "use hyprctl dispatch 'hl.dsp.…':\n" + "\n".join(offenders)
    )


def test_app_keys_go_through_omarchy_launchers(tmp_path: Path) -> None:
    """The keymap must not name app binaries — Omarchy's defaults own that.

    A binding that execs `firefox` pins the choice in a file the user cannot
    reach from Omarchy's own menu, and skips uwsm-app scoping and the
    cwd-inheriting terminal launch that come with the native launchers.
    """
    code = "\n".join(
        ln
        for ln in (REPO_ROOT / "hypr" / "bindings.lua").read_text().splitlines()
        if not ln.lstrip().startswith("--")
    )
    # `{ omarchy = "nautilus" }` is the launcher idiom (omarchy-launch-nautilus,
    # default/hypr/helpers.lua) — the one quoted app name that is not a pin.
    launchers = re.findall(r'\{ omarchy = "([a-z-]+)" \}', code)
    assert set(launchers) == {"terminal", "browser", "editor", "nautilus"}
    code = re.sub(r'\{ omarchy = "[a-z-]+" \}', "", code)
    # The quoted form is the point: `exec_cmd("nautilus")` pins the app, while
    # the launcher resolves the user's default.
    for binary in ('"firefox"', '"nautilus"', '"code"', '"kitty"', '"dolphin"'):
        assert binary not in code, f"{binary} is an Omarchy default, not a keymap constant"


def test_default_apps_are_seeded_once(tmp_path: Path) -> None:
    """Seeded to hyprconf's picks on first install, then the user's to change."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    calls = _calls(env)
    assert any(c.startswith("omarchy-default-browser firefox") for c in calls)
    assert any(c.startswith("omarchy-default-editor code") for c in calls)

    env["calls"].write_text("")
    _run(env, "--no-update")
    # Not `omarchy-default-*`: stage_terminal calls omarchy-default-terminal on
    # every run by design, to check what the default already is.
    again = _calls(env)
    assert not any(c.startswith("omarchy-default-browser") for c in again)
    assert not any(c.startswith("omarchy-default-editor") for c in again)


# ---------------------------------------------------------------------------
# Wallpapers
# ---------------------------------------------------------------------------


def test_wallpapers_land_where_omarchy_looks_for_them(tmp_path: Path) -> None:
    """Omarchy only ever scans two directories, both keyed to the ACTIVE theme.

    omarchy-theme-bg-next and omarchy-theme-bg-switcher both read the active
    theme's own backgrounds/ plus ~/.config/omarchy/backgrounds/<theme>/. A
    wallpaper filed anywhere else simply never appears in the switcher, with no
    error to explain why — which is what happened when hyprconf's gruvbox shot
    lived in hyprconf's own theme directory.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    seeded = env["home"] / ".config" / "omarchy" / "backgrounds" / "gruvbox" / "gruvbox.jpg"
    assert seeded.is_file()
    assert seeded.read_bytes() == (REPO_ROOT / "wallpapers" / "gruvbox.jpg").read_bytes()


def test_a_replaced_wallpaper_is_left_alone(tmp_path: Path) -> None:
    """Backgrounds are seeded, not synced — the folder is the user's to curate."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    seeded = env["home"] / ".config" / "omarchy" / "backgrounds" / "gruvbox" / "gruvbox.jpg"
    seeded.write_bytes(b"my own wallpaper")
    _run(env, "--no-update")
    assert seeded.read_bytes() == b"my own wallpaper"


# ---------------------------------------------------------------------------
# The system font
# ---------------------------------------------------------------------------


def test_font_is_set_once_and_then_left_alone(tmp_path: Path) -> None:
    """Which font is running is the user's call after the first install.

    The post-update hook re-runs this installer after every Omarchy update, so
    a stage that re-asserted the font would quietly undo `omarchy font set` —
    the same way stage_theme used to take the theme back.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert any(c.startswith("omarchy-font-set") for c in _calls(env))

    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-font-set") for c in _calls(env))


def test_font_stage_is_skipped_when_the_font_is_not_installed(tmp_path: Path) -> None:
    """A cosmetic stage must not take the whole install down.

    omarchy-font-set exits 1 on a family fc-list does not know, which under
    `set -e` would abort the run — so the family is resolved from fc-list first
    and the stage bows out if it is missing.
    """
    env = _setup(tmp_path)
    _stub(env["bins"] / "fc-list", env["calls"], 'echo "DejaVu Sans Mono"')
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not any(c.startswith("omarchy-font-set") for c in _calls(env))
    # No marker written, so it will apply once the package really is there.
    assert not (env["home"] / ".local" / "state" / "hyprconf" / "font-applied").exists()


# ---------------------------------------------------------------------------
# The bar widget
# ---------------------------------------------------------------------------


def test_bar_widget_never_sizes_itself_off_its_parent() -> None:
    """A widget whose implicit size reads `parent` is invisible on the bar.

    Omarchy's ModuleSlot takes its height from the widget's implicit size, so
    `implicitHeight: parent.height` closes a binding loop. QML breaks a loop by
    dropping the binding, which leaves the widget zero-height — it still loads,
    logs nothing at any verbosity, and paints nothing. That silence is what
    makes this worth a test rather than a comment: there is no error to grep
    for, only a gap in the bar.
    """
    offenders = [
        f"{qml.relative_to(REPO_ROOT)}: {line.strip()}"
        for qml in sorted((REPO_ROOT / "plugins").glob("*/*.qml"))
        for line in _code_only_qml(qml.read_text()).splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]
    assert list((REPO_ROOT / "plugins").glob("*/*.qml")), "no plugin QML found"
    assert not offenders, (
        "Bar widget implicit size must not depend on `parent` (binding loop -> "
        "zero size -> invisible widget):\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_sync_runs_omarchy_update_and_never_pacman(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--sync")
    calls = _calls(env)
    assert any(c.startswith("omarchy-update") for c in calls)
    assert not any(c.startswith("pacman") for c in calls)


def test_no_packages_skips_every_privileged_stage(tmp_path: Path) -> None:
    """--no-packages is "no sudo": the hook passes it inside omarchy-update.
    Packages, Firefox (Omarchy's installer + the policy) and VS Code all sit
    behind it — with nothing installed and a terminal to prompt on, none of
    the four privileged commands may run."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-pkg-present", env["calls"], "exit 1")
    proc = _run(env, "--no-packages", "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    for privileged in (
        "omarchy-pkg-add",
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
        "omarchy-pkg-drop",
        "sudo",
    ):
        assert privileged not in _commands(env), privileged


def test_unknown_flag_is_rejected(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    proc = _run(env, "--definitely-not-a-flag")
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# The hooks
# ---------------------------------------------------------------------------


def _theme_state(env: dict) -> Path:
    """An active Omarchy theme as omarchy-theme-set leaves it: theme.name plus
    colors.toml (what the omarchy-theme-refresh fake renders templates from)."""
    theme = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme.parent / "theme.name").write_text("lumon\n")
    (theme / "colors.toml").write_text(
        'mode = "dark"\nbackground = "#16242d"\nforeground = "#d6e2ee"\naccent = "#8bc9eb"\n'
        'dark_background = "#101b21"\nlighter_background = "#1b2d40"\n'
    )
    return theme


def _firefox_profile(env: dict) -> Path:
    ff = env["home"] / ".config" / "mozilla" / "firefox"
    profile = ff / "abc.default-release"
    profile.mkdir(parents=True, exist_ok=True)
    (ff / "profiles.ini").write_text(
        "[Profile0]\nName=default-release\nIsRelative=1\nPath=abc.default-release\n"
        "[Install4F96]\nDefault=abc.default-release\n"
    )
    return profile


def test_hooks_are_installed_through_omarchy_hook_install(tmp_path: Path) -> None:
    """omarchy-update runs ~/.config/omarchy/hooks/post-update.d/* and
    omarchy-theme-set ends with `omarchy-hook theme-set <name>`, which runs
    theme-set.d/*. Each hook is rendered — the checkout path resolved (the
    theme-set one puts lib/ on PYTHONPATH) — under its final basename and
    handed to Omarchy's own `omarchy-hook-install <type> <file>` (4.0.0-1:
    mkdir -p, cp under the basename, chmod 755). The theme-set hook must
    never abort a theme switch (no set -e) or escalate."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    hooks = env["home"] / ".config" / "omarchy" / "hooks"
    installs = [c for c in _calls(env) if c.startswith("omarchy-hook-install ")]
    assert sorted(c.split()[1] for c in installs) == ["post-update", "theme-set"]
    for name in ("post-update", "theme-set"):
        call = next(c for c in installs if c.split()[1] == name)
        assert call.split()[2].endswith("/10-hyprconf"), call  # installed under its basename
        installed = hooks / f"{name}.d" / "10-hyprconf"
        body = installed.read_text()
        assert "@HYPRCONF_DIR@" not in body and str(REPO_ROOT) in body, name
        assert os.access(installed, os.X_OK), name
    code = _code_only((hooks / "theme-set.d" / "10-hyprconf").read_text())
    assert "set -e" not in code and "sudo" not in code and "omarchy-update" not in code
    assert "hyprconf.firefox_theme" in code


def test_hooks_fall_back_to_a_plain_copy_without_omarchy_hook_install(tmp_path: Path) -> None:
    """The same three steps by hand only when Omarchy has no installer
    command — the hooks must land either way, byte for byte the same."""
    env = _setup(tmp_path)
    (env["bins"] / "omarchy-hook-install").unlink()
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    hooks = env["home"] / ".config" / "omarchy" / "hooks"
    for name in ("post-update", "theme-set"):
        installed = hooks / f"{name}.d" / "10-hyprconf"
        expected = (
            (REPO_ROOT / "hooks" / f"{name}.d" / "10-hyprconf")
            .read_text()
            .replace("@HYPRCONF_DIR@", str(REPO_ROOT))
        )
        assert installed.read_text() == expected, name
        assert os.access(installed, os.X_OK), name


def test_theme_set_hook_extends_the_theme_to_firefox(tmp_path: Path) -> None:
    """Omarchy renders hyprconf's user template (themed/userChrome.css.tpl,
    installed by stage_themed and rendered through omarchy-theme-refresh) into
    the current theme dir; the hook copies it into the Firefox profile and
    merges user.js. install.sh runs the hook once for the active theme, so
    nothing waits for the next switch. VS Code is Omarchy's own now
    (omarchy-theme-set-vscode in omarchy-theme-set's fan-out)."""
    env = _setup(tmp_path)
    _real_jq(env)
    _theme_state(env)
    profile = _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr

    rendered = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme" / "userChrome.css"
    assert rendered.is_file(), "stage_themed did not get the template rendered"
    css = (profile / "chrome" / "userChrome.css").read_text()
    assert "--toolbar-bgcolor: #16242d !important;" in css
    js = (profile / "user.js").read_text()
    assert 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' in js
    assert 'user_pref("ui.systemUsesDarkTheme", 1);' in js

    # Idempotent: a second run (the post-update hook's) changes nothing.
    before = _tree_hash(profile)
    _run(env, "--no-update")
    assert _tree_hash(profile) == before


def test_theme_stage_is_a_noop_without_an_active_theme(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (
        env["home"] / ".config" / "mozilla" / "firefox" / "abc.default-release" / "user.js"
    ).exists()
    assert "omarchy-theme-refresh" not in _commands(env)


# ---------------------------------------------------------------------------
# Theme templates — Omarchy's user template seam
# ---------------------------------------------------------------------------


def _themed_checkout(tmp_path: Path) -> tuple[Path, str]:
    """A throwaway checkout with one throwaway user template beside whatever
    themed/ ships, so the stage is exercised whether or not the repo carries
    a template of its own yet. Returns (checkout, template name)."""
    repo = _checkout(tmp_path)
    (repo / "themed").mkdir(exist_ok=True)
    name = "hyprconf-test.css.tpl"
    (repo / "themed" / name).write_text("body { color: {{ foreground }}; }\n")
    return repo, name


def test_templates_are_installed_and_rendered_through_omarchy_theme_refresh(
    tmp_path: Path,
) -> None:
    """Every repo themed/*.tpl lands in ~/.config/omarchy/themed/ (Omarchy's
    user template dir, rendered on each theme set ahead of default/themed),
    and the render for the theme active right now is Omarchy's own
    omarchy-theme-refresh — run only when a template changed or its render is
    missing, so the hook's re-runs cost nothing; never omarchy-theme-set
    with another name."""
    env = _setup(tmp_path)
    repo, name = _themed_checkout(tmp_path)
    _theme_state(env)
    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    installed = env["home"] / ".config" / "omarchy" / "themed" / name
    assert installed.read_bytes() == (repo / "themed" / name).read_bytes()
    assert _commands(env).count("omarchy-theme-refresh") == 1
    assert "omarchy-theme-set" not in _commands(env)
    rendered = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme" / name[:-4]
    assert rendered.read_text() == "body { color: #d6e2ee; }\n"

    env["calls"].write_text("")
    _run(env, "--no-update", install_sh=repo / "install.sh")
    assert "omarchy-theme-refresh" not in _commands(env)

    (repo / "themed" / name).write_text("body { color: {{ accent }}; }\n")
    env["calls"].write_text("")
    _run(env, "--no-update", install_sh=repo / "install.sh")
    assert installed.read_text() == "body { color: {{ accent }}; }\n"
    assert _commands(env).count("omarchy-theme-refresh") == 1
    assert rendered.read_text() == "body { color: #8bc9eb; }\n"


def test_templates_wait_for_a_theme_when_none_is_active(tmp_path: Path) -> None:
    """Installed either way; with no theme.name there is nothing to refresh
    — the next `omarchy theme set` renders it."""
    env = _setup(tmp_path)
    repo, name = _themed_checkout(tmp_path)
    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    assert (env["home"] / ".config" / "omarchy" / "themed" / name).is_file()
    assert "omarchy-theme-refresh" not in _commands(env)
    assert "next omarchy theme set" in proc.stdout


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
    """Every shell script the overlay ships: install.sh and the bash files
    under the installed trees. Walked on disk, not `git ls-files`, so the scan
    needs no git and no ownership trust (CI's root-run git refuses the
    runner-owned workspace)."""
    roots = ["install.sh", "hypr", "bin", "hooks", "zsh", "kitty", "plugins"]
    paths: list[Path] = []
    for root in roots:
        top = REPO_ROOT / root
        paths.extend([top] if top.is_file() else sorted(top.rglob("*")))
    return [p for p in paths if p.is_file() and p.suffix in {".sh", ""}]


# `pacman -Syu` is blocked by Omarchy's ALPM guard, `pacman -R` would
# dismantle Omarchy, and the AUR is never used (AGENTS.md: official
# repositories only).
FORBIDDEN_TOKENS = (
    "pacman -Syu",
    "pacman -Syyu",
    "pacman -R",
    "yay ",
    "makepkg",
    "omarchy-pkg-aur-add",
)


def test_overlay_never_uses_forbidden_pacman_or_aur_forms() -> None:
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        for token in FORBIDDEN_TOKENS:
            assert token not in code, f"{script}: {token}"


# ---------------------------------------------------------------------------
# The Firefox policy — the overlay's one write outside $HOME
# ---------------------------------------------------------------------------


def _policy_env(tmp_path: Path, env: dict) -> tuple[Path, dict[str, str]]:
    """A sudo that actually runs its command (so the policy lands in the
    tree), the real jq (the merge), and the policy path under tmp_path."""
    _real_jq(env)
    _stub(env["bins"] / "sudo", env["calls"], '"$@"')
    policies = tmp_path / "etc" / "firefox" / "policies"
    return policies, {"_HYPRCONF_ASSUME_TTY": "1", "_HYPRCONF_FIREFOX_POLICIES": str(policies)}


def test_firefox_policy_is_omarchys_merged_under_ours_via_sudo_when_interactive(
    tmp_path: Path,
) -> None:
    """Firefox reads enterprise policies only from root-owned paths, so the
    file goes through sudo to (an overridden) /etc/firefox/policies — which
    takes precedence over the distribution/ file omarchy-install-browser
    writes, and would shadow Omarchy's prefs. So what lands is Omarchy's
    default/firefox/policies.json merged UNDER infra/firefox/policies.json:
    every Omarchy pref survives, every hyprconf key is there, and ours wins
    on a shared key. A matching file is left alone, so a re-run — and every
    hyprsync after it — never re-prompts for a password."""
    env = _setup(tmp_path)
    policies, extra = _policy_env(tmp_path, env)
    proc = _run(env, "--no-update", extra_env=extra)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-browser" not in _commands(env)  # firefox is present

    installed = json.loads((policies / "policies.json").read_text())["policies"]
    ours = json.loads((REPO_ROOT / "infra" / "firefox" / "policies.json").read_text())["policies"]
    theirs = OMARCHY_FIREFOX_POLICY["policies"]["Preferences"]
    for key, value in ours.items():
        if key != "Preferences":
            assert installed[key] == value, key
    for pref, value in ours["Preferences"].items():
        assert installed["Preferences"][pref] == value, pref
    assert (
        installed["Preferences"]["media.ffmpeg.vaapi.enabled"]
        == theirs["media.ffmpeg.vaapi.enabled"]
    )
    assert (
        installed["Preferences"]["widget.wayland.fractional-scale.enabled"]
        == theirs["widget.wayland.fractional-scale.enabled"]
    )
    assert installed["Preferences"]["browser.compactmode.show"]["Value"] is True  # ours

    env["calls"].write_text("")
    _run(env, "--no-update", extra_env=extra)
    assert "sudo" not in _commands(env)


def test_firefox_is_installed_through_omarchys_installer_when_absent(tmp_path: Path) -> None:
    """No firefox package (omarchy-pkg-present fails): `omarchy-install-browser
    firefox` — Omarchy's own flow: omarchy-pkg-add, its prefs under
    /usr/lib/firefox/distribution, MOZ_ENABLE_WAYLAND — runs before the policy
    lands; never a bare omarchy-pkg-add firefox from the package list."""
    env = _setup(tmp_path)
    policies, extra = _policy_env(tmp_path, env)
    _stub(env["bins"] / "omarchy-pkg-present", env["calls"], '[ "$1" != firefox ]')
    proc = _run(env, "--no-update", extra_env=extra)
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-install-browser firefox" in calls
    assert calls.index("omarchy-install-browser firefox") < next(
        i for i, c in enumerate(calls) if c.startswith("sudo install")
    )
    assert (policies / "policies.json").is_file()
    pkg_add = [c for c in calls if c.startswith("omarchy-pkg-add")]
    assert pkg_add and not any("firefox" in c.split() for c in pkg_add)


def test_firefox_policy_is_skipped_without_a_terminal(tmp_path: Path) -> None:
    """The post-update hook runs non-interactively inside omarchy-update; a
    sudo password prompt there would stall the whole update, so no tty means
    no attempt — neither the policy nor Omarchy's installer."""
    env = _setup(tmp_path)
    _real_jq(env)
    _stub(env["bins"] / "omarchy-pkg-present", env["calls"], '[ "$1" != firefox ]')
    policies = tmp_path / "etc" / "firefox" / "policies"
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_FIREFOX_POLICIES": str(policies)})
    assert proc.returncode == 0, proc.stderr
    assert not (policies / "policies.json").exists()
    assert "sudo" not in _commands(env)
    assert "omarchy-install-browser" not in _commands(env)


def test_firefox_policy_sits_behind_the_no_packages_gate(tmp_path: Path) -> None:
    """--no-packages means "no sudo" — the hook passes it for that reason, so
    the other privileged stages must honor it too."""
    env = _setup(tmp_path)
    policies, extra = _policy_env(tmp_path, env)
    _run(env, "--no-update", "--no-packages", extra_env=extra)
    assert "sudo" not in _commands(env)
    assert not (policies / "policies.json").exists()


# ---------------------------------------------------------------------------
# VS Code — Omarchy's own installer, the Code - OSS conflict cleared first
# ---------------------------------------------------------------------------


def _packages(env: dict, present: tuple[str, ...]) -> None:
    """omarchy-pkg-present answering for exactly these package names. The
    VS Code installer stub then makes visual-studio-code-bin present, the way
    the real one does (omarchy-pkg-add inside)."""
    marker = env["home"].parent / "vscode-installed"
    names = " ".join(present)
    _stub(
        env["bins"] / "omarchy-pkg-present",
        env["calls"],
        f'case " {names} " in *" $1 "*) exit 0;; esac; '
        f'[ "$1" = visual-studio-code-bin ] && [ -e "{marker}" ]',
    )
    _stub(env["bins"] / "omarchy-install-editor-vscode", env["calls"], f'touch "{marker}"')


def test_vscode_already_present_is_left_alone(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _packages(env, ("firefox", "visual-studio-code-bin"))
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-editor-vscode" not in _commands(env)
    assert "omarchy-pkg-drop" not in _commands(env)


def test_code_oss_is_dropped_before_omarchys_vscode_installer(tmp_path: Path) -> None:
    """Arch's `code` (Code - OSS, what v4.0.0–v4.2.0 installed) conflicts with
    visual-studio-code-bin (pacman -Si: Conflicts With: code) and Omarchy's
    installer is a plain `pacman -S --noconfirm --needed` that a conflict
    fails — so Code - OSS goes first, through Omarchy's own omarchy-pkg-drop
    (only names pacman -Qq lists, --noconfirm), then
    omarchy-install-editor-vscode, which opens VS Code once at the end: the
    log says so. Nothing runs pacman itself."""
    env = _setup(tmp_path)
    _packages(env, ("firefox", "code"))
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-pkg-drop code" in calls
    assert "omarchy-install-editor-vscode " in calls
    assert calls.index("omarchy-pkg-drop code") < calls.index("omarchy-install-editor-vscode ")
    assert "pacman" not in _commands(env)
    assert "opens VS Code once" in proc.stdout
    assert "~/.vscode-oss stay, not migrated" in proc.stdout
    pkg_add = [c for c in calls if c.startswith("omarchy-pkg-add")]
    assert pkg_add and not any("code" in c.split() for c in pkg_add)

    env["calls"].write_text("")  # installed now: nothing more to do
    _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert "omarchy-install-editor-vscode" not in _commands(env)
    assert "omarchy-pkg-drop" not in _commands(env)


def test_vscode_is_installed_without_a_drop_when_no_editor_is_present(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _packages(env, ("firefox",))
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-editor-vscode" in _commands(env)
    assert "omarchy-pkg-drop" not in _commands(env)


def test_vscode_install_waits_for_a_terminal(tmp_path: Path) -> None:
    """Both Omarchy commands prompt for sudo; the hook's non-interactive run
    must not start either."""
    env = _setup(tmp_path)
    _packages(env, ("firefox", "code"))
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-editor-vscode" not in _commands(env)
    assert "omarchy-pkg-drop" not in _commands(env)


# A model of the shell's config handling, enough for the bar-widget stages.
# omarchy-plugin-enable and omarchy-bar mutate the config the shell holds in
# memory (a state file) at once and persist it to shell.json later —
# shell.qml writes through a FileView and re-reads the file on change — the
# way PluginRegistry.qml (Omarchy 4.0.0-1) does it: setEnabled swaps a copy
# into the stock entry (settings kept) or places it; setBarWidget sets a key
# on the entry.
SHELL_MODEL = """\
import json
import os
import sys
import time

state, shell_json, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
verb, args = sys.argv[4], sys.argv[5:]


def entry_id(entry):
    return entry if isinstance(entry, str) else str(entry.get("id", ""))


def load():
    # Memory, unless the file is newer: the shell re-reads it on change.
    paths = [p for p in (state, shell_json) if os.path.exists(p)]
    if not paths:
        return {}
    with open(max(paths, key=os.path.getmtime)) as f:
        return json.load(f)


def persist(config):
    text = json.dumps(config)
    with open(state, "w") as f:
        f.write(text)
    if delay <= 0:
        with open(shell_json, "w") as f:
            f.write(text)
        return
    if os.fork() == 0:  # the FileView write lands later; the caller is answered now
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)
        time.sleep(delay)
        with open(shell_json, "w") as f:
            f.write(text)
        os._exit(0)


def find(layout, wid):
    for section, entries in layout.items():
        for index, entry in enumerate(entries):
            if entry_id(entry) == wid:
                return section, index
    return None


def placement(flags):
    it = iter(flags)
    return {flag.lstrip("-"): value for flag, value in zip(it, it)}


config = load()
layout = config.setdefault("bar", {}).setdefault("layout", {})
for section in ("left", "center", "right"):
    layout.setdefault(section, [])
wid = args[1] if verb == "bar" else args[0]
stock = "omarchy." + wid.split(".", 1)[1]  # every copy clones the same-named stock widget

if verb == "enable" and not find(layout, wid):
    where = find(layout, stock)
    if where:
        entry = layout[where[0]][where[1]]
        replacement = dict(entry) if isinstance(entry, dict) else {}
        replacement["id"] = wid
        layout[where[0]][where[1]] = replacement
    else:
        wanted = placement(args[1:])
        relative = wanted.get("after") or wanted.get("before")
        if relative:
            where = find(layout, relative)
            if not where:
                sys.exit(1)  # "could not find target widget"
            layout[where[0]].insert(where[1] + (1 if "after" in wanted else 0), {"id": wid})
        else:
            layout[wanted.get("section", "center")].append({"id": wid})
elif verb == "bar" and args[0] == "set":
    where = find(layout, wid)
    if not where or not isinstance(layout[where[0]][where[1]], dict):
        sys.exit(1)
    layout[where[0]][where[1]][args[2]] = args[3]
persist(config)
"""


def _shell_model(env: dict, *, delay: float = 0) -> Path:
    """Put SHELL_MODEL behind omarchy-plugin-enable and omarchy-bar (still
    recording stubs), with the real jq the installer reads the file with.
    Returns the shell's "memory" file."""
    _real_jq(env)
    root = env["home"].parent
    model = root / "shell_model.py"
    model.write_text(SHELL_MODEL)
    state = root / "shell-state.json"
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    shell_json.parent.mkdir(parents=True, exist_ok=True)
    for name, verb in (("omarchy-plugin-enable", "enable"), ("omarchy-bar", "bar")):
        _stub(
            env["bins"] / name,
            env["calls"],
            f'exec "{sys.executable}" "{model}" "{state}" "{shell_json}" {delay} {verb} "$@"',
        )
    return state


def test_shell_json_edits_wait_for_the_shells_asynchronous_writes(tmp_path: Path) -> None:
    """The shell answers an enable or a set at once but persists shell.json
    from a FileView some time later (shell.qml). A read-modify-write on the
    file straight after — the anchor edit — would land on a stale copy and
    then be overwritten by the pending write. The installer waits for the
    last thing it asked the shell for to be on disk first; modelled with a
    0.2 s write delay under the real wait budget."""
    env = _setup(tmp_path)
    state = _shell_model(env, delay=0.2)
    _plugin_fixtures(env, tmp_path)
    # Discovered at once, so the enable's own discovery wait does not eat the budget.
    _stub(
        env["bins"] / "omarchy-plugin-list",
        env["calls"],
        'echo \'[{"id":"hyprconf.clock"},{"id":"hyprconf.workspaces"},'
        '{"id":"hyprconf.active-window"},{"id":"hyprconf.resources"}]\'',
    )
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    shell_json.write_text(
        json.dumps(
            {
                "bar": {
                    "centerAnchor": "omarchy.clock",
                    "layout": {"left": [], "center": [{"id": "omarchy.clock"}], "right": []},
                }
            }
        )
    )
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_PLUGIN_WAIT": "40"})
    assert proc.returncode == 0, proc.stderr
    for _ in range(100):  # the model's last pending write
        if shell_json.read_text() == state.read_text():
            break
        time.sleep(0.05)
    data = json.loads(shell_json.read_text())
    assert data["bar"]["centerAnchor"] == "hyprconf.clock"
    assert {"id": "hyprconf.clock", "format": "hh:mm:ss AP"} in data["bar"]["layout"]["center"]
    assert "omarchy.clock" not in [e["id"] for e in data["bar"]["layout"]["center"]]


def test_defaults_marker_waits_for_a_successful_seed(tmp_path: Path) -> None:
    """A first run with --no-packages (firefox/code not installed yet) must not
    record the defaults as applied, or they would never be seeded."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-default-browser", env["calls"], "exit 1")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (env["home"] / ".local" / "state" / "hyprconf" / "defaults-applied").exists()
    _stub(env["bins"] / "omarchy-default-browser", env["calls"], "exit 0")
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert any(c.startswith("omarchy-default-browser firefox") for c in _calls(env))
    assert (env["home"] / ".local" / "state" / "hyprconf" / "defaults-applied").exists()


def test_every_shipped_tool_lands_on_path(tmp_path: Path) -> None:
    """Every bin/hyprconf-* file, installed by glob with the checkout path
    substituted, so a new tool is one file."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    shipped = sorted(p.name for p in (REPO_ROOT / "bin").glob("hyprconf-*"))
    assert {
        "hyprconf-stats",
        "hyprconf-gpu-info",
        "hyprconf-yubikey",
        "hyprconf-firefox-theme",
        "hyprconf-vulkan-gpu",
        "hyprconf-monitor-preset",
        "hyprconf-gaps",
    } <= set(shipped)
    for name in shipped:
        installed = env["home"] / ".local" / "bin" / name
        assert os.access(installed, os.X_OK), name
        expected = (REPO_ROOT / "bin" / name).read_text().replace("@HYPRCONF_DIR@", str(REPO_ROOT))
        assert installed.read_text() == expected, name


# ---------------------------------------------------------------------------
# The bar clock
# ---------------------------------------------------------------------------


def _plugin_fixtures(env: dict, tmp_path: Path) -> Path:
    """Real jq + a fake omarchy.clock plugin source behind a catalog stub.

    The stage resolves the plugin source from omarchy-plugin-catalog at
    runtime and rewrites its manifest with jq, so these tests need the real
    jq and a catalog pointing at a source tree under tmp_path."""
    _real_jq(env)
    src = tmp_path / "clock-src"
    src.mkdir(exist_ok=True)
    (src / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": "omarchy.clock",
                "name": "Clock",
                "version": "1.0.0",
                "kinds": ["bar-widget"],
                "entryPoints": {"barWidget": "BarWidget.qml"},
                "barWidget": {"displayName": "Clock"},
                "omarchy": {"clonePaths": [{"source": "x", "target": "x"}]},
            }
        )
    )
    (src / "BarWidget.qml").write_text("precision: SystemClock.Minutes\n")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            [
                {
                    "id": "omarchy.clock",
                    "firstParty": True,
                    "sourceDir": str(src),
                    "manifestPath": str(src / "manifest.json"),
                    "name": "Clock",
                },
            ]
        )
    )
    _stub(env["bins"] / "omarchy-plugin-catalog", env["calls"], f'cat "{catalog}"')
    return src


def test_clock_is_copied_patched_and_set_once(tmp_path: Path) -> None:
    """The stock widget samples SystemClock at Minutes precision (shell/
    plugins/panels/clock/BarWidget.qml), so a seconds format freezes. The
    stage copies the widget to the project's own hyprconf.clock — source
    resolved from omarchy-plugin-catalog at runtime, manifest rewritten the
    way omarchy-plugin-clone's update_manifest does — and patches the copy.
    Set-once: the marker is what keeps the post-update hook from reverting a
    format the user later picked."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-enable hyprconf.clock" in calls
    assert "omarchy-bar set hyprconf.clock format hh:mm:ss AP" in calls
    # The copy is patched before the enable, and the rescan that precedes it
    # hot-reloads plugin code (shell/README.md) — no shell restart.
    assert "omarchy-shell shell rescanPlugins" in calls
    assert "omarchy-restart-shell" not in _commands(env)

    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.clock"
    widget = (plug / "BarWidget.qml").read_text()
    assert "SystemClock.Seconds" in widget
    assert "SystemClock.Minutes" not in widget
    manifest = json.loads((plug / "manifest.json").read_text())
    assert manifest["id"] == "hyprconf.clock"
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.clock"
    assert "clonePaths" not in manifest["omarchy"]
    assert manifest["barWidget"]["displayName"] == "hyprconf Clock"

    env["calls"].write_text("")
    _run(env, "--no-update")
    again = _calls(env)
    assert not any(c.startswith("omarchy-plugin-catalog") for c in again)
    assert not any(c.startswith("omarchy-bar") for c in again)


def test_clock_widget_id_carries_no_username() -> None:
    """omarchy-plugin-clone names clones <username>.<id> with no way to
    choose otherwise — a username must never leak into shipped
    configuration. The stage builds the copy itself under the project's own
    namespace, beside hyprconf.resources."""
    code = _code_only(INSTALL_SH.read_text())
    assert "hyprconf.clock" in code
    assert "omarchy-plugin-clone" not in code
    assert "id -un" not in code
    assert "$USER" not in code and "${USER" not in code


def test_bar_widget_enables_retry_until_the_shell_can_answer(tmp_path: Path) -> None:
    """omarchy-plugin-enable talks to the live shell; a TTY or SSH run has
    none to talk to. The failure must not abort the install, no set-once
    marker may be written — so the next in-session run tries every widget
    again — and nothing is set on a clock that never landed."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    _stub(env["bins"] / "omarchy-plugin-enable", env["calls"], "exit 1")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    state = env["home"] / ".local" / "state" / "hyprconf"
    for widget in ("resources", "clock", "workspaces", "active-window"):
        assert not (state / f"{widget}-applied").exists(), widget
        assert f"hyprconf.{widget}" in proc.stderr, widget
    assert not any(c.startswith("omarchy-bar") for c in _calls(env))


def test_discovery_wait_is_skipped_when_there_is_no_shell_to_ask(tmp_path: Path) -> None:
    """omarchy-plugin-list (set -e) exits 1 the moment omarchy-shell reports
    "is not running" — identically on every poll — so a TTY first run must
    not sit through the full discovery wait once per widget before every
    enable fails anyway: one list call per enable, then the retry warning."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    _stub(env["bins"] / "omarchy-plugin-list", env["calls"], "exit 1")
    _stub(env["bins"] / "omarchy-plugin-enable", env["calls"], "exit 1")
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_PLUGIN_WAIT": "40"})
    assert proc.returncode == 0, proc.stderr
    commands = _commands(env)
    assert commands.count("omarchy-plugin-enable") == 4
    assert commands.count("omarchy-plugin-list") == 4


def test_workspaces_widget_is_the_overlays_own_plugin(tmp_path: Path) -> None:
    """The stock widget hardcodes pills 1-5, caps ids at 10 and reads no
    settings, so the overlay ships its own widget (plugins/hyprconf-workspaces)
    as a clonedFrom copy: the shell swaps it into the stock widget's slot and
    `omarchy plugin disable hyprconf.workspaces` restores stock. Synced on
    every run — a git pull updates it — and enabled once."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-plugin-enable hyprconf.workspaces" in _calls(env)

    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.workspaces"
    src = REPO_ROOT / "plugins" / "hyprconf-workspaces"
    for f in src.iterdir():
        assert (plug / f.name).read_bytes() == f.read_bytes(), f.name
    manifest = json.loads((plug / "manifest.json").read_text())
    assert manifest["id"] == "hyprconf.workspaces"
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.workspaces"
    assert manifest["entryPoints"]["barWidget"] == "Workspaces.qml"
    assert manifest["kinds"] == ["bar-widget"]

    # Synced, not seeded: a stale installed copy comes back to the repo's, and
    # the running shell rescans so it draws the new one.
    (plug / "Workspaces.qml").write_text("// stale\n")
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert (plug / "Workspaces.qml").read_bytes() == (src / "Workspaces.qml").read_bytes()
    assert "omarchy-shell shell rescanPlugins" in _calls(env)
    # …but enabled once only, so a later `omarchy plugin disable` sticks.
    assert "omarchy-plugin-enable hyprconf.workspaces" not in _calls(env)


def test_plugin_sync_stages_a_sibling_temp_dir_and_rescans(tmp_path: Path) -> None:
    """The copy is staged in a temp dir beside the plugin dirs and moved into
    place — omarchy-plugin-clone's pattern (mktemp -d under the plugins dir,
    cp -aL, mv) — so the shell's directory watch never scans a half-copied
    plugin; no staging dir is left behind. Then `omarchy-shell shell
    rescanPlugins` (what omarchy-plugin-update runs after a fast-forward) —
    it hot-reloads plugin code — and omarchy-restart-shell only when no
    shell answers that."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    plugins = env["home"] / ".config" / "omarchy" / "plugins"
    assert not list(plugins.glob(".hyprconf.*"))
    assert "omarchy-shell shell rescanPlugins" in _calls(env)
    assert "omarchy-restart-shell" not in _commands(env)

    # Nothing changed: no rescan, no restart.
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert "omarchy-shell shell rescanPlugins" not in _calls(env)
    assert "omarchy-restart-shell" not in _commands(env)

    # A changed widget with no shell to rescan: the restart is the fallback.
    _stub(env["bins"] / "omarchy-shell", env["calls"], "exit 1")
    (plugins / "hyprconf.resources" / "Widget.qml").write_text("// stale\n")
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert "omarchy-shell shell rescanPlugins" in _calls(env)
    assert "omarchy-restart-shell" in _commands(env)
    assert not list(plugins.glob(".hyprconf.*"))


def test_resources_widget_declares_its_bar_section_in_the_manifest() -> None:
    """Placement is the manifest's barWidget.defaultSection ("right"), which
    the shell honours on an enable with no placement (PluginRegistry.qml
    defaultBarWidgetSection, 4.0.0-1; omarchy-plugin-validate checks the
    value) — so the enable carries no --section argument."""
    manifest = json.loads(
        (REPO_ROOT / "plugins" / "hyprconf-resources" / "manifest.json").read_text()
    )
    assert manifest["barWidget"]["defaultSection"] == "right"
    assert "--section" not in _code_only(INSTALL_SH.read_text())


def test_installed_plugins_pass_omarchy_plugin_validate(tmp_path: Path) -> None:
    """Omarchy's own validator (the checks PluginRegistry.qml enforces:
    schemaVersion, required fields, entry points that exist, a valid
    defaultSection, no symlinks, no omarchy.* id) over every plugin dir the
    overlay puts under ~/.config/omarchy/plugins — the three shipped copies
    and the hyprconf.clock copy. Real when installed; a pure check."""
    if not PLUGIN_VALIDATE.is_file():
        pytest.skip("no installed omarchy-plugin-validate")
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    assert _run(env, "--no-update").returncode == 0
    plugins = env["home"] / ".config" / "omarchy" / "plugins"
    dirs = sorted(p for p in plugins.iterdir() if p.is_dir())
    assert [p.name for p in dirs] == [
        "hyprconf.active-window",
        "hyprconf.clock",
        "hyprconf.resources",
        "hyprconf.workspaces",
    ]
    for plugin in dirs:
        proc = subprocess.run(
            ["bash", str(PLUGIN_VALIDATE), str(plugin)],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin", "HOME": str(env["home"])},
        )
        assert proc.returncode == 0, f"{plugin.name}: {proc.stderr}"


def test_workspaces_widget_shows_only_active_workspaces_on_two_lines() -> None:
    """What the widget promises, pinned statically: no fixed pill set and no
    id cap (only workspaces Hyprland has), two rows, hyprconf's Pac-Man on the
    focused workspace, and the stock IPC id kept as moduleName."""
    qml = _code_only_qml(
        (REPO_ROOT / "plugins" / "hyprconf-workspaces" / "Workspaces.qml").read_text()
    )
    assert "[1, 2, 3, 4, 5]" not in qml and "id <= 10" not in qml
    assert "\\u{F0BAF}" in qml  # nf-md-pac_man, hyprconf's focused marker
    assert re.search(r"columns:.*Math\.ceil\(root\.ids\.length / 2\)", qml)
    assert 'moduleName: "omarchy.workspaces"' in qml


def test_window_title_is_a_two_line_clone_enabled_once_after_the_workspaces(
    tmp_path: Path,
) -> None:
    """hyprconf's bar drew the focused window's title beside the workspaces.
    Omarchy's stock omarchy.active-window does that on one line; the overlay
    ships a clonedFrom copy that lays the same character budget out on two
    lines. Synced every run, enabled once with no placement of its own — the
    manifest's defaultSection is left, where the shell anchors a new widget
    after omarchy.workspaces, clone-resolved (PluginRegistry.qml barTarget,
    4.0.0-1); a later `omarchy plugin disable` survives the hook's re-runs."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-enable hyprconf.active-window" in calls
    assert not any("omarchy-plugin-enable omarchy.active-window" in c for c in calls)
    assert (env["home"] / ".local" / "state" / "hyprconf" / "active-window-applied").exists()
    manifest = json.loads(
        (REPO_ROOT / "plugins" / "hyprconf-active-window" / "manifest.json").read_text()
    )
    assert manifest["barWidget"]["defaultSection"] == "left"

    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.active-window"
    src = REPO_ROOT / "plugins" / "hyprconf-active-window"
    for f in src.iterdir():
        assert (plug / f.name).read_bytes() == f.read_bytes(), f.name
    manifest = json.loads((plug / "manifest.json").read_text())
    assert manifest["id"] == "hyprconf.active-window"
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.active-window"
    assert manifest["entryPoints"]["barWidget"] == "ActiveWindow.qml"

    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(
        "active-window" in c for c in _calls(env) if c.startswith("omarchy-plugin-enable")
    )


def test_window_title_widget_lays_the_same_budget_out_on_two_lines() -> None:
    """Pinned statically: the stock maxWidth budget (body-size, one line) is
    rendered as two caption-size lines of half the width, word-wrapped and
    elided on the second line; stock behaviours (tooltip, click focus,
    middle-click close, hidden when nothing is focused / vertical bar) and
    the stock IPC id are kept."""
    qml = _code_only_qml(
        (REPO_ROOT / "plugins" / "hyprconf-active-window" / "ActiveWindow.qml").read_text()
    )
    assert 'moduleName: "omarchy.active-window"' in qml
    assert 'setting("maxWidth", 280)' in qml
    assert "maximumLineCount: 2" in qml and "font.pixelSize: Style.font.caption" in qml
    assert "root.toplevel.close()" in qml and "root.toplevel.activate()" in qml
    assert "showTooltip(root, root.title)" in qml


def test_resources_widget_layout_is_fixed_width_and_ordered() -> None:
    """Two aligned lines — CPU temp/util · RAM · upload over GPU temp/util ·
    VRAM · download; the thermometer is the solid Material Design glyph
    (U+F050F), not the Weather-Icons outline (U+E350) that rendered as a
    hairline; the GPU cells read the structured fields the feeder emits (no
    pre-rendered "text")."""
    qml = _code_only_qml((REPO_ROOT / "plugins" / "hyprconf-resources" / "Widget.qml").read_text())
    assert "\\u{F050F}" in qml and "\\ue350" not in qml.lower()
    # Row-major order: the upload cell precedes every GPU cell, the download cell is last.
    up = qml.index('"↑ " + root.netUp')
    down = qml.index('"↓ " + root.netDown')
    gpu = qml.index('root.glyphGpu + " " + root.tempText')
    assert up < gpu < down
    for field in ("j.util", "j.temp", "j.vram_used", "j.vram_total", "j.tooltip"):
        assert field in qml, field
    assert "j.text" not in qml


def test_plugin_qml_parses() -> None:
    """A QML syntax error is an empty bar slot with nothing in any log.
    `qmllint --bare` parses without the module imports (exit 0 with import
    warnings on a good file, non-zero on a broken one)."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    for qml in sorted((REPO_ROOT / "plugins").glob("*/*.qml")):
        proc = subprocess.run([qmllint, "--bare", str(qml)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{qml.name}: {proc.stderr}"


def test_bar_plugins_are_enabled_once_so_disable_sticks(tmp_path: Path) -> None:
    """The post-update hook re-runs the installer after every Omarchy update;
    an unconditional enable would undo `omarchy plugin disable <id>` each
    time. The first run enables, later runs leave the choice alone."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert "omarchy-plugin-enable hyprconf.resources" in _calls(env)
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-plugin-enable") for c in _calls(env))


# ---------------------------------------------------------------------------
# Workspace placement on a preset switch
# ---------------------------------------------------------------------------


def test_monitor_preset_moves_existing_workspaces(tmp_path: Path) -> None:
    """Workspace rules only place FUTURE workspaces; a switch must move
    today's. On reload Hyprland leaves existing workspaces on whatever monitor
    they already occupy, so without an explicit move the kitchen hotkey
    enabled the right outputs while workspaces 1-6 stayed on the bedroom TV.
    The move uses the Lua dispatch form — hl.dsp.workspace.move, verified on
    Hyprland 0.56.2 — for the same reason the dpms recovery does (the
    two-token dispatch is a parse error there, per its own scan above)."""
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")

    env["calls"].write_text("")
    proc = _switch(env, "kitchen")
    assert proc.returncode == 0, proc.stderr

    rules = re.findall(
        r'hl\.workspace_rule\(\{ workspace = "(\d+)", monitor = "([^"]+)" \}\)',
        (REPO_ROOT / "hypr" / "pcMonitors.kitchen.lua").read_text(),
    )
    assert rules, "kitchen preset carries no workspace rules"
    calls = _calls(env)
    for ws, mon in rules:
        expected = (
            f'hyprctl dispatch hl.dsp.workspace.move({{ workspace = {ws}, monitor = "{mon}" }})'
        )
        assert expected in calls, expected


def test_clock_copy_takes_the_center_anchor_with_it(tmp_path: Path) -> None:
    """canonicalWidgetId does no clone resolution (shell/Commons/Util.qml — a
    plain string cast), so a centerAnchor left at omarchy.clock matches
    nothing once the bar swaps to hyprconf.clock, and the clock drifts
    off-center. The stage follows the anchor — but only while it still
    points at the stock id, so a user's own anchor choice is never
    overridden."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    shell_json.parent.mkdir(parents=True, exist_ok=True)
    shell_json.write_text('{"bar": {"centerAnchor": "omarchy.clock"}}')
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "hyprconf.clock"

    # An anchor the user re-pointed later is left alone (marker aside, the
    # guard itself only matches the stock id).
    shell_json.write_text('{"bar": {"centerAnchor": "omarchy.weather"}}')
    _run(env, "--no-update")
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "omarchy.weather"


# ---------------------------------------------------------------------------
# The `omarchy refresh` guard
# ---------------------------------------------------------------------------


STOCK_BINDINGS = "-- Keep only your personal keybinding overrides here.\n"


def _stock_templates(env: dict) -> Path:
    """Omarchy's config/ templates — what omarchy-refresh-config copies from."""
    templates = env["omarchy_path"] / "config" / "hypr"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "bindings.lua").write_text(STOCK_BINDINGS)
    (templates / "monitors.lua").write_text('hl.monitor({ output = "", mode = "preferred" })\n')
    return templates


def _refresh_config(env: dict, templates: Path, name: str) -> None:
    """What omarchy-refresh-config does to ~/.config/hypr/<name>: cp -f from the
    template. cp -f follows a symlink, so with the overlay installed this
    writes THROUGH the link into the checkout. Reproduced with the real cp."""
    subprocess.run(
        ["cp", "-f", str(templates / name), str(env["home"] / ".config" / "hypr" / name)],
        check=True,
        timeout=30,
    )


def test_refresh_through_the_symlink_is_undone_from_git(tmp_path: Path) -> None:
    """`omarchy refresh hyprland` replaces every ~/.config/hypr/*.lua with the
    stock template via cp -f, which follows the overlay's symlinks straight
    into the checkout — hypr/bindings.lua became Omarchy's commented template
    and every hyprconf hotkey vanished (observed on Omarchy 4.0.0-1). A
    re-run must notice the checkout holds a byte-identical stock template and
    put the committed file back."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    templates = _stock_templates(env)
    committed = (repo / "hypr" / "bindings.lua").read_text()
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0

    _refresh_config(env, templates, "bindings.lua")
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS  # the damage

    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == committed
    assert "stock template" in proc.stderr and "restored" in proc.stderr
    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert live.is_symlink() and live.read_text() == committed


def test_a_real_edit_in_the_checkout_is_never_reverted(tmp_path: Path) -> None:
    """The guard keys on byte-identity with the stock template and nothing
    else: an edit made through the symlink is the user editing their own
    dotfiles, exactly what the links are for."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    _stock_templates(env)
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0

    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    edited = live.read_text() + '\no.bind("SUPER + SHIFT + R", "SSH", "kitty -e ssh box")\n'
    live.write_text(edited)  # through the symlink, like an editor would

    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == edited
    assert "stock template" not in proc.stderr


def test_guard_reports_when_git_cannot_repair(tmp_path: Path) -> None:
    """No git to restore from (a tarball, or the stub in every other test):
    the clobber is still reported, and the run still completes."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    templates = _stock_templates(env)
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0
    _refresh_config(env, templates, "bindings.lua")

    proc = _run(env, "--no-update", install_sh=repo / "install.sh")  # git is the no-op stub
    assert proc.returncode == 0, proc.stderr
    assert "could not be" in proc.stderr and "git" in proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS


def test_omarchy_refresh_of_monitors_lua_never_reaches_a_preset(tmp_path: Path) -> None:
    """With the chosen preset in the toggles file, monitors.lua is Omarchy's
    own real file, so `omarchy refresh config hypr/monitors.lua` lands where
    Omarchy means it to — on monitors.lua — and neither the preset nor the
    toggle is touched. (Under the old symlink flow it wrote the template
    through the link onto the preset itself.)"""
    env = _setup(tmp_path)
    templates = _stock_templates(env)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    assert _run(env, "--no-update").returncode == 0
    assert _switch(env, "bedroom").returncode == 0
    preset = hypr.joinpath("pcMonitors.bedroom.lua").read_text()

    _refresh_config(env, templates, "monitors.lua")
    stock = (templates / "monitors.lua").read_text()
    assert hypr.joinpath("monitors.lua").read_text() == stock
    assert hypr.joinpath("pcMonitors.bedroom.lua").read_text() == preset
    assert (env["home"] / TOGGLE).read_text() == preset
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "stock" not in proc.stderr


def test_old_hotkey_script_copies_are_swept(tmp_path: Path) -> None:
    """v4.0.0–v4.2.0 copied switch_monitor.sh and adjust-gaps to
    ~/.config/hypr/scripts/; both are ~/.local/bin tools now, so the copies go
    — and the directory with them only when nothing else is in it."""
    env = _setup(tmp_path)
    old = env["home"] / ".config" / "hypr" / "scripts"
    old.mkdir(parents=True)
    (old / "switch_monitor.sh").write_text("#!/bin/bash\n")
    (old / "adjust-gaps").write_text("#!/bin/bash\n")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not old.exists()
    assert "switch_monitor.sh — it is ~/.local/bin/hyprconf-monitor-preset now" in proc.stdout
    assert "adjust-gaps — it is ~/.local/bin/hyprconf-gaps now" in proc.stdout

    old.mkdir()
    (old / "adjust-gaps").write_text("#!/bin/bash\n")
    (old / "mine.sh").write_text("#!/bin/bash\n")  # the user's own script
    _run(env, "--no-update")
    assert sorted(p.name for p in old.iterdir()) == ["mine.sh"]


# ---------------------------------------------------------------------------
# The curl path — `bash <(curl -fsSL hyprconf.sh)` serves install.sh alone
# ---------------------------------------------------------------------------

# A git that really clones a LOCAL repository (the throwaway checkout under
# tmp_path — never the network) and is otherwise GIT_PASSTHROUGH: a clone of
# a URL only makes the directory, a pull is a no-op.
GIT_LOCAL_CLONE = """\
if [ "$1" = clone ]; then
  src="${@: -2:1}"
  if [ -d "$src" ]; then exec "$(PATH=/usr/bin:/bin command -v git)" "$@"; fi
  mkdir -p "${@: -1}"; exit 0
fi
case " $* " in *" pull "*) exit 0 ;; esac
exec "$(PATH=/usr/bin:/bin command -v git)" "$@"
"""


def _served_copy(tmp_path: Path) -> Path:
    """install.sh alone, the way hyprconf.sh serves it to curl: no payload beside it."""
    served = tmp_path / "served"
    served.mkdir()
    shutil.copy2(INSTALL_SH, served / "install.sh")
    return served / "install.sh"


def _stable_checkout(tmp_path: Path) -> Path:
    """_checkout on `stable`, the branch the curl path clones by default."""
    repo = _checkout(tmp_path)
    subprocess.run(["git", "branch", "-M", "stable"], cwd=repo, check=True, timeout=30)
    return repo


def test_curl_path_clones_the_checkout_and_hands_over_to_it(tmp_path: Path) -> None:
    """Run with nothing beside it, install.sh clones HYPRCONF_REPO (branch
    stable, single-branch) into HYPRCONF_DIR and execs that checkout's own
    copy with the same arguments — which then applies every stage from the
    checkout, not from /dev/fd."""
    env = _setup(tmp_path)
    repo = _stable_checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_LOCAL_CLONE)
    target = tmp_path / "hyprconf-dir"
    proc = _run(
        env,
        "--no-update",
        extra_env={"HYPRCONF_REPO": str(repo), "HYPRCONF_DIR": str(target)},
        install_sh=_served_copy(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert f"git clone --branch stable --single-branch {repo} {target}" in _calls(env)
    assert (target / ".git").is_dir()
    for name in PAYLOAD:
        assert (target / name).exists(), name
    # The stages ran, from the checkout: the tools and hooks resolve to it and
    # the override links point into it.
    assert "omarchy-default-terminal kitty" in _calls(env)
    assert env["pkg_add"] in _commands(env)
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    assert f'HYPRCONF_DIR="{target}"' in hook.read_text()
    bindings = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert Path(os.readlink(bindings)) == target / "hypr" / "bindings.lua"
    assert (env["home"] / ".zshrc").exists()
    assert "omarchy-update" not in _commands(env)


def test_curl_path_refuses_a_box_without_omarchy_before_cloning(tmp_path: Path) -> None:
    """Preflight runs BEFORE the clone: a machine that is not Omarchy gets the
    refusal and nothing else — no checkout lands on it."""
    env = _setup(tmp_path, with_omarchy=False)
    repo = _stable_checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_LOCAL_CLONE)
    target = tmp_path / "hyprconf-dir"
    proc = _run(
        env,
        extra_env={"HYPRCONF_REPO": str(repo), "HYPRCONF_DIR": str(target)},
        install_sh=_served_copy(tmp_path),
    )
    assert proc.returncode != 0
    assert "omarchy" in proc.stderr.lower()
    assert not target.exists()
    assert not any(c.startswith("git clone") for c in _calls(env))
    assert not (env["home"] / ".zshrc").exists()


def test_curl_path_reuses_an_existing_checkout_without_pulling(tmp_path: Path) -> None:
    """A checkout already at HYPRCONF_DIR is used as it is: no clone over it,
    and no pull either — updating it is --sync's job, not the bootstrap's."""
    env = _setup(tmp_path)
    repo = _stable_checkout(tmp_path)
    git = ["git", "-C", str(repo)]
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    _stub(env["bins"] / "git", env["calls"], GIT_LOCAL_CLONE)
    proc = _run(
        env,
        "--no-update",
        extra_env={"HYPRCONF_REPO": str(tmp_path / "never-cloned"), "HYPRCONF_DIR": str(repo)},
        install_sh=_served_copy(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert "existing checkout" in proc.stdout
    assert not any(c.startswith("git clone") and c.endswith(f" {repo}") for c in _calls(env))
    assert not any(" pull " in f" {c} " for c in _calls(env))
    assert not (tmp_path / "never-cloned").exists()
    after = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    assert after.stdout == head.stdout
    status = subprocess.run([*git, "status", "--porcelain"], capture_output=True, text=True)
    assert status.stdout == ""
    # …and the stages ran from that checkout.
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    assert f'HYPRCONF_DIR="{repo}"' in hook.read_text()


def test_curl_path_help_and_bad_options_never_clone(tmp_path: Path) -> None:
    """The option loop runs before the hand-over, so --help (and a typo) answer
    from the served copy without touching the machine."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_LOCAL_CLONE)
    target = tmp_path / "hyprconf-dir"
    served = _served_copy(tmp_path)
    proc = _run(env, "--help", extra_env={"HYPRCONF_DIR": str(target)}, install_sh=served)
    assert proc.returncode == 0
    assert "bash <(curl -fsSL hyprconf.sh)" in proc.stdout
    assert "HYPRCONF_REPO" in proc.stdout
    proc = _run(env, "--bogus", extra_env={"HYPRCONF_DIR": str(target)}, install_sh=served)
    assert proc.returncode != 0
    assert not target.exists()
    assert _calls(env) == []


# ---------------------------------------------------------------------------
# The banner
# ---------------------------------------------------------------------------


def _banner_rows() -> list[str]:
    """The six logo rows of assets/banner.svg — the same art the installer prints."""
    svg = (REPO_ROOT / "assets" / "banner.svg").read_text()
    rows = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
    assert len(rows) == 6, rows
    return rows


def test_banner_prints_on_a_terminal_only_and_matches_the_svg(tmp_path: Path) -> None:
    """The .hyprconf banner (the retired assets/banner.sh, ported): once, at
    the start, on a terminal only — this suite sees nothing — and never
    inside omarchy-update, where the post-update hook runs it: stdout IS a
    tty there (omarchy-update re-execs itself under script(1), Omarchy
    4.0.0-1), so the gate is the OMARCHY_UPDATE_LOGGED marker that re-exec
    exports. The logo rows are byte-identical to assets/banner.svg, colours
    only on a real tty, and never a screen clear (the update's output must
    stay on screen)."""
    env = _setup(tmp_path)
    quiet = _run(env, "--no-update")
    assert quiet.returncode == 0, quiet.stderr
    assert "[ SYS ]" not in quiet.stdout

    hooked = _run(
        env,
        "--no-update",
        "--no-packages",
        extra_env={"_HYPRCONF_ASSUME_TTY": "1", "OMARCHY_UPDATE_LOGGED": "1"},
    )
    assert hooked.returncode == 0, hooked.stderr
    assert "[ SYS ]" not in hooked.stdout

    loud = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert loud.returncode == 0, loud.stderr
    assert "\n".join(_banner_rows()) + "\n" in loud.stdout
    assert loud.stdout.count("[ SYS ] omarchy overlay") == 1
    assert "hyprconf.sh" in loud.stdout
    assert "[ SYS ] origin: github.com/ak4dev/.hyprconf   branch: " in loud.stdout
    assert loud.stdout.index("[ SYS ]") < loud.stdout.index("==> ")
    assert "\x1b" not in loud.stdout  # not a real tty: no colour codes
    assert "[2J" not in INSTALL_SH.read_text() and "\x1b[2J" not in loud.stdout

    # The curl path prints it in the served copy and marks it shown, so the
    # checkout's copy it execs does not print it a second time.
    again = _run(
        env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1", "HYPRCONF_BANNER_SHOWN": "1"}
    )
    assert again.returncode == 0, again.stderr
    assert "[ SYS ]" not in again.stdout


# ---------------------------------------------------------------------------
# The menu — Proton VPN under Install > Service, through Omarchy's extension file
# ---------------------------------------------------------------------------

MENU_EXT = Path(".config") / "omarchy" / "extensions" / "omarchy-menu.jsonc"
MENU_BEGIN = "  // >>> hyprconf >>>"
MENU_END = "  // <<< hyprconf <<<"
PROTONVPN_ROW = {
    "icon": "󰦝",
    "label": "Proton VPN",
    "when": "! omarchy-pkg-present proton-vpn-gtk-app",
    "action": "omarchy-launch-floating-terminal-with-presentation hyprconf-install-service-protonvpn",
}


def _menu_items(path: Path) -> dict:
    """The extension file the way Omarchy's menu reads it: a port of
    shell/plugins/menu/MenuModel.js stripJsonc (4.0.0-1) — whole-line //
    comments go, then the comma before a } or ] — and JSON.parse. Anything
    that fails here makes the shell silently drop the WHOLE user file."""
    raw = path.read_text()
    stripped = re.sub(r"^\s*//[^\n]*(\n|$)", "", raw, flags=re.M)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
    return json.loads(stripped)


def test_menu_row_is_added_through_omarchys_extension_file(tmp_path: Path) -> None:
    """A fresh box: the user extension file is seeded from Omarchy's template
    (all comments, kept byte for byte), the managed block sits right before
    the closing brace, and the result parses the way the menu parses it —
    with the one row exactly as Omarchy shapes its own install.service rows.
    The row's action is the tool stage_bin put on ~/.local/bin."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    ext = env["home"] / MENU_EXT
    text = ext.read_text()
    assert text.startswith(OMARCHY_MENU_EXTENSION.rsplit("}", 1)[0])
    lines = text.splitlines()
    assert lines.count(MENU_BEGIN) == 1 and lines.count(MENU_END) == 1
    assert lines[-3:] == [
        '  "install.service.protonvpn": {"icon":"󰦝","label":"Proton VPN",'
        '"when":"! omarchy-pkg-present proton-vpn-gtk-app",'
        '"action":"omarchy-launch-floating-terminal-with-presentation'
        ' hyprconf-install-service-protonvpn"},',
        MENU_END,
        "}",
    ]
    assert lines[-4] == MENU_BEGIN
    assert _menu_items(ext) == {"install.service.protonvpn": PROTONVPN_ROW}

    tool = env["home"] / ".local" / "bin" / "hyprconf-install-service-protonvpn"
    assert os.access(tool, os.X_OK)
    assert PROTONVPN_ROW["action"].endswith(" " + tool.name)
    # `when` hides the row once the package the tool installs is present.
    assert "omarchy-pkg-add proton-vpn-gtk-app proton-vpn-cli" in tool.read_text()


@pytest.mark.parametrize(
    ("before", "after_head"),
    [
        # The last entry has no trailing comma: it gets one.
        (
            '{\n  "personal": {"icon":"x","label":"P"}\n}\n',
            '{\n  "personal": {"icon":"x","label":"P"},\n',
        ),
        # It already has one, and a comment follows: nothing doubled, nothing lost.
        (
            '{\n  "personal": {"icon":"x","label":"P"},\n  // mine\n}\n',
            '{\n  "personal": {"icon":"x","label":"P"},\n  // mine\n',
        ),
        # A multi-line entry: the comma lands on its closing brace.
        (
            '{\n  "personal": {\n    "icon": "x",\n    "label": "P"\n  }\n}\n',
            '{\n  "personal": {\n    "icon": "x",\n    "label": "P"\n  },\n',
        ),
    ],
    ids=["no-comma", "comma-then-comment", "multi-line"],
)
def test_menu_block_keeps_the_users_file_parseable(
    tmp_path: Path, before: str, after_head: str
) -> None:
    """The block goes last, so the user's own last entry must end with a comma
    for the file to stay valid — it is given one when it has none, and never
    a second. Everything the user wrote survives, in place."""
    env = _setup(tmp_path)
    ext = env["home"] / MENU_EXT
    ext.parent.mkdir(parents=True)
    ext.write_text(before)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    text = ext.read_text()
    assert text.startswith(after_head + MENU_BEGIN + "\n")
    assert text.endswith(MENU_END + "\n}\n")
    assert _menu_items(ext) == {
        "personal": {"icon": "x", "label": "P"},
        "install.service.protonvpn": PROTONVPN_ROW,
    }


def test_menu_block_is_byte_stable_and_left_alone_when_current(tmp_path: Path) -> None:
    """A re-run (the post-update hook, every Omarchy update) changes nothing
    and does not even touch the file: the menu watches it, and a rewrite of
    the same bytes would still make it reparse."""
    env = _setup(tmp_path)
    assert _run(env, "--no-update").returncode == 0
    ext = env["home"] / MENU_EXT
    before = ext.read_bytes()
    os.utime(ext, (0, 0))
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert ext.read_bytes() == before
    assert ext.stat().st_mtime == 0
    # No temp file left beside it either.
    assert sorted(p.name for p in ext.parent.iterdir()) == ["omarchy-menu.jsonc"]


def test_menu_block_is_byte_stable_from_the_first_run_after_trailing_blank_lines(
    tmp_path: Path,
) -> None:
    """Blank lines after the closing brace: the first run already writes what
    a re-run would (strip_managed_block drops trailing newlines before the
    block goes back in), so the second run is the no-op — not the third."""
    env = _setup(tmp_path)
    ext = env["home"] / MENU_EXT
    ext.parent.mkdir(parents=True)
    ext.write_text('{\n  "personal": {"icon":"x","label":"P"}\n}\n\n\n')
    first = _run(env, "--no-update")
    assert first.returncode == 0, first.stderr
    text = ext.read_text()
    assert text.endswith(MENU_END + "\n}\n")
    assert _menu_items(ext) == {
        "personal": {"icon": "x", "label": "P"},
        "install.service.protonvpn": PROTONVPN_ROW,
    }
    second = _run(env, "--no-update")
    assert second.returncode == 0, second.stderr
    assert ext.read_text() == text


def test_an_empty_extension_file_is_seeded_like_a_missing_one(tmp_path: Path) -> None:
    """A touched or truncated omarchy-menu.jsonc holds nothing of the user's
    and is unparseable for the menu as it is: it is seeded from Omarchy's
    template and gets the block, the same as when it is absent — not left
    empty with a warning."""
    env = _setup(tmp_path)
    ext = env["home"] / MENU_EXT
    ext.parent.mkdir(parents=True)
    ext.write_text("")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "closing-brace" not in proc.stderr
    assert ext.read_text().startswith(OMARCHY_MENU_EXTENSION.rsplit("}", 1)[0])
    assert _menu_items(ext) == {"install.service.protonvpn": PROTONVPN_ROW}


def test_a_stale_menu_block_is_replaced_not_duplicated(tmp_path: Path) -> None:
    """An older overlay's block — a different row, an extra row — is stripped
    before the current one goes in: one marker pair, and only today's rows."""
    env = _setup(tmp_path)
    ext = env["home"] / MENU_EXT
    ext.parent.mkdir(parents=True)
    ext.write_text(
        '{\n  "personal": {"icon":"x","label":"P"},\n'
        + MENU_BEGIN
        + '\n  "install.service.protonvpn": {"icon":"old","label":"Old"},\n'
        + '  "gone.row": {"label":"gone"},\n'
        + MENU_END
        + "\n}\n"
    )
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    text = ext.read_text()
    assert text.count(MENU_BEGIN) == 1 and text.count(MENU_END) == 1
    assert "gone.row" not in text and '"old"' not in text
    assert _menu_items(ext) == {
        "personal": {"icon": "x", "label": "P"},
        "install.service.protonvpn": PROTONVPN_ROW,
    }


def test_menu_stage_leaves_a_file_it_cannot_extend_alone(tmp_path: Path) -> None:
    """No closing-brace line to put the block before (a one-line file): the
    file is left exactly as it is, with a warning — a wrong edit would make
    the menu drop every row the user has."""
    env = _setup(tmp_path)
    ext = env["home"] / MENU_EXT
    ext.parent.mkdir(parents=True)
    ext.write_text('{"personal": {"icon":"x"}}\n')
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert ext.read_text() == '{"personal": {"icon":"x"}}\n'
    assert "closing-brace" in proc.stderr
    assert sorted(p.name for p in ext.parent.iterdir()) == ["omarchy-menu.jsonc"]


def test_menu_stage_writes_through_a_symlinked_extension_file(tmp_path: Path) -> None:
    """A stow-style link into a dotfiles checkout stays a link; the file
    behind it gets the block."""
    env = _setup(tmp_path)
    real = tmp_path / "dotfiles" / "omarchy-menu.jsonc"
    real.parent.mkdir()
    real.write_text("{\n}\n")
    ext = env["home"] / MENU_EXT
    ext.parent.mkdir(parents=True)
    ext.symlink_to(real)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert ext.is_symlink() and ext.resolve() == real.resolve()
    assert _menu_items(real) == {"install.service.protonvpn": PROTONVPN_ROW}
    assert sorted(p.name for p in real.parent.iterdir()) == ["omarchy-menu.jsonc"]


def test_protonvpn_installer_installs_both_official_packages_through_omarchy(
    tmp_path: Path,
) -> None:
    """bin/hyprconf-install-service-protonvpn mirrors omarchy-install-service-
    nordvpn: one omarchy-pkg-add with both extra-repo packages, then how to
    sign in. No daemon to enable, no group, no reboot — and a failed install
    stops it before it claims success."""
    env = _setup(tmp_path)
    child = _child_env(env)
    assert os.access(PROTONVPN_INSTALLER, os.X_OK)
    proc = subprocess.run(
        ["bash", str(PROTONVPN_INSTALLER)], env=child, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    assert _calls(env) == ["omarchy-pkg-add proton-vpn-gtk-app proton-vpn-cli"]
    assert "protonvpn login" in proc.stdout
    code = _code_only(PROTONVPN_INSTALLER.read_text())
    for forbidden in ("systemctl", "usermod", "reboot", "gum "):
        assert forbidden not in code, forbidden

    _stub(env["bins"] / "omarchy-pkg-add", env["calls"], "exit 1")
    proc = subprocess.run(
        ["bash", str(PROTONVPN_INSTALLER)], env=child, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode != 0
    assert "installed" not in proc.stdout


# ---------------------------------------------------------------------------
# The dual-GPU Vulkan check — bin/hyprconf-vulkan-gpu, run by stage_vulkan_gpu
# ---------------------------------------------------------------------------

VULKAN_ENV_D = Path(".config") / "uwsm" / "env.d" / "50-hyprconf-vulkan-gpu"
VULKAN_IGNORED = Path(".local") / "state" / "hyprconf" / "vulkan-gpu-ignored"
VULKAN_STAGE = "==> Dual-GPU Vulkan check (hyprconf-vulkan-gpu)"

# The failing box: two NVIDIA GPUs, the displays on the SECOND by PCI order —
# Vulkan device 1, which Wine never binds a monitor to (Xwayland exposes no
# RandR providers). The sysfs of the box the fix was verified on.
DUAL_NVIDIA = (
    ("0000:04:00.0", "0x10de", "0x2484", 0),
    ("0000:0a:00.0", "0x10de", "0x2b85", 2),
)


def _gum_stub(env: dict, answer: str) -> None:
    """A gum whose `choose` picks the option whose first word is `answer` —
    the prompt's three start with Fix, Alt and Ignore — the way a keypress
    would, skipping the flags; every other verb is a no-op."""
    _stub(
        env["bins"] / "gum",
        env["calls"],
        '[ "$1" = choose ] || exit 0\n'
        "shift\n"
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in\n'
        "    --*=*) shift; continue ;;\n"
        "    --header|--cursor|--selected|--height|--limit) shift 2; continue ;;\n"
        "    --*) shift; continue ;;\n"
        f'    "{answer}"|"{answer} "*) printf "%s\\n" "$1"; exit 0 ;;\n'
        "  esac\n"
        "  shift\n"
        "done\n"
        "exit 1",
    )


def test_dual_gpu_box_is_pinned_when_the_user_says_fix(tmp_path: Path) -> None:
    """A terminal run on the failing box explains the problem, asks, and on
    Fix writes the uwsm env.d file every uwsm-launched app inherits at the
    next login (Omarchy's own override seam, /usr/share/uwsm/env.d/10-omarchy):
    the loader filter and device select for the display GPU, plus the NVIDIA
    PRIME pair — both required together — because another NVIDIA GPU precedes
    it. The real tool runs, as installed by stage_bin, against a fake sysfs;
    the file is sh-sourceable the way uwsm sources it (prepare-env.sh,
    source_dir); the run goes on past the stage; a re-run finds the box
    configured and asks nothing."""
    env = _setup(tmp_path)
    _sysfs(env, DUAL_NVIDIA)
    _gum_stub(env, "Fix")
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    assert VULKAN_STAGE in proc.stdout
    assert "WARNING: hyprconf-vulkan-gpu" not in proc.stderr
    assert any(c.startswith("gum choose") for c in _calls(env))
    assert "VK_LOADER_DEVICE_ID_FILTER=0x2b85" in proc.stdout + proc.stderr
    assert "re-login" in proc.stdout + proc.stderr

    env_d = env["home"] / VULKAN_ENV_D
    code = [ln for ln in env_d.read_text().splitlines() if ln and not ln.startswith("#")]
    assert code == [
        "export VK_LOADER_DEVICE_ID_FILTER=0x2b85",
        "export VK_LOADER_DEVICE_SELECT=10de:2b85",
        "export __NV_PRIME_RENDER_OFFLOAD=1",
        "export __VK_LAYER_NV_optimus=NVIDIA_only",
    ]
    sourced = subprocess.run(
        ["sh", "-c", f'. "{env_d}" && printf %s "$VK_LOADER_DEVICE_ID_FILTER"'],
        capture_output=True,
        text=True,
        timeout=30,
        env=_child_env(env),
    )
    assert sourced.returncode == 0 and sourced.stdout == "0x2b85", sourced.stderr
    assert not (env["home"] / VULKAN_IGNORED).exists()
    assert (env["home"] / ".zshrc").exists()  # a stage well after this one

    env["calls"].write_text("")
    before = env_d.read_bytes()
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    assert "gum" not in _commands(env)
    assert env_d.read_bytes() == before


@pytest.mark.parametrize(
    ("args", "extra_env"),
    [
        (("--no-update",), {}),
        (
            ("--no-update", "--no-packages"),
            {"_HYPRCONF_ASSUME_TTY": "1", "OMARCHY_UPDATE_LOGGED": "1"},
        ),
    ],
    ids=["no-terminal", "omarchy-update"],
)
def test_dual_gpu_check_never_prompts_without_a_terminal(
    tmp_path: Path, args: tuple[str, ...], extra_env: dict[str, str]
) -> None:
    """The post-update hook runs `install.sh --no-update --no-packages` inside
    omarchy-update, which re-execs itself under script(1) (bin/omarchy-update,
    Omarchy 4.0.0-1): every child has a pty, so the tty test passes, while
    `-y` promises to ask nothing — the OMARCHY_UPDATE_LOGGED marker it exports
    is the gate, as for the banner. That run, and a plain non-interactive one,
    on the failing box: nothing asked, nothing written — no env.d file, no
    marker — and exit 0; the tool leaves one line naming itself, so the
    stage's own log line is not the only trace."""
    env = _setup(tmp_path)
    _sysfs(env, DUAL_NVIDIA)
    _gum_stub(env, "Fix")
    proc = _run(env, *args, extra_env=extra_env)
    assert proc.returncode == 0, proc.stderr
    assert VULKAN_STAGE in proc.stdout
    assert "WARNING: hyprconf-vulkan-gpu" not in proc.stderr
    assert (proc.stdout + proc.stderr).count("hyprconf-vulkan-gpu") >= 2
    assert "gum" not in _commands(env)
    assert not (env["home"] / ".config" / "uwsm").exists()
    assert not (env["home"] / VULKAN_IGNORED).exists()


def test_single_gpu_box_has_nothing_to_pin(tmp_path: Path) -> None:
    """One GPU (the harness default) and a terminal to ask on: the diagnosis,
    not the tty gate, is what stops it — no prompt, no file, no marker."""
    env = _setup(tmp_path)
    _gum_stub(env, "Fix")
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ASSUME_TTY": "1"})
    assert proc.returncode == 0, proc.stderr
    assert VULKAN_STAGE in proc.stdout
    assert "WARNING: hyprconf-vulkan-gpu" not in proc.stderr
    assert "gum" not in _commands(env)
    assert not (env["home"] / ".config" / "uwsm").exists()
    assert not (env["home"] / VULKAN_IGNORED).exists()


def test_a_failing_dual_gpu_check_is_a_warning_not_a_failed_install(tmp_path: Path) -> None:
    """The tool exits 1 when it cannot read sysfs (the PCI seam pointed at a
    file). A diagnosis must never take an install down: the run warns,
    naming the tool, and every later stage still runs."""
    env = _setup(tmp_path)
    _gum_stub(env, "Fix")
    broken = tmp_path / "not-a-sysfs"
    broken.write_text("")
    proc = _run(
        env,
        "--no-update",
        extra_env={"_HYPRCONF_ASSUME_TTY": "1", "_HYPRCONF_SYS_PCI": str(broken)},
    )
    assert proc.returncode == 0, proc.stderr
    assert VULKAN_STAGE in proc.stdout
    assert "WARNING: hyprconf-vulkan-gpu" in proc.stderr
    assert "gum" not in _commands(env)
    assert not (env["home"] / ".config" / "uwsm").exists()
    assert (env["home"] / MENU_EXT).exists()  # the very next stage
    assert (env["home"] / ".zshrc").exists()
