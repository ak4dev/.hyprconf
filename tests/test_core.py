"""install.sh — the core: the curl bootstrap, the flags, the module loop, the
~/.local/bin/hyprconf link, the post-update hook and --undo, plus the
restraint a whole run is held to (AGENTS.md › Hard rules, 6). Each module's
behaviour is its own suite's; here the modules run whole, through the core,
on the `box` fixture (conftest.py) — `live` adds the few fakes a full run
needs to take every module's real path. Hermetic: a throwaway HOME, /etc and
$OMARCHY_PATH per test, and nothing reaches the network or the desktop.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import Box, git

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "install.sh"
MODULES = REPO_ROOT / "modules"
HOOK = REPO_ROOT / "hooks" / "10-hyprconf"
INSTALLED_HOOK = ".config/omarchy/hooks/post-update.d/10-hyprconf"
LINK = ".local/bin/hyprconf"
ONE_LINER = "bash <(curl -fsSL --proto '=https' https://hyprconf.sh)"


def modules() -> list[str]:
    """Every module. The core runs them in its glob's order, which the modules
    may not depend on (each is order-free): a run is held to every one of
    them, once, never to a particular order."""
    return sorted(p.parent.name for p in MODULES.glob("*/install"))


def ran(proc: subprocess.CompletedProcess) -> list[str]:
    """The module names the core announced, in order (`==> <name>`)."""
    return [m for m in re.findall(r"^==> (\S+)$", proc.stdout, re.M) if m in modules()]


def undone(proc: subprocess.CompletedProcess) -> list[str]:
    return re.findall(r"^==> undo (\S+)$", proc.stdout, re.M)


# ---- the fakes a full run needs ---------------------------------------------

# bin/omarchy-hook-install:27-29 (Omarchy 4.0.3-1): mkdir -p the .d dir, cp under
# the file's basename, chmod 755 — reproduced so the installed hook can be run.
HOOK_INSTALL = (
    'd="$HOME/.config/omarchy/hooks/$1.d"; mkdir -p "$d"; cp "$2" "$d/${2##*/}"; '
    'chmod 755 "$d/${2##*/}"\n'
)

# bin/omarchy-shell-config, the helper modules/idle SOURCES: functions only, no
# `exit` — the shared recording fake's `exit 0` would end the module's subshell
# before commit() ran. The three functions that path reaches, transcribed.
SHELL_CONFIG = """\
CONFIG_FILE="$HOME/.config/omarchy/shell.json"
DEFAULTS_FILE="$OMARCHY_PATH/config/omarchy/shell.json"
fail() { echo "omarchy-shell-config: $*" >&2; exit 1; }
refresh_shell_config() { omarchy-shell shell reloadConfig >/dev/null 2>&1 || true; }
source_file() { if [[ -s $CONFIG_FILE ]]; then echo "$CONFIG_FILE"; else echo "$DEFAULTS_FILE"; fi; }
commit() {
  local program="$1" tmp; shift
  mkdir -p "$(dirname "$CONFIG_FILE")"; tmp=$(mktemp)
  jq -S -e "$@" "$program" "$(source_file)" > "$tmp" || fail "could not update shell config"
  mv "$tmp" "$CONFIG_FILE"; refresh_shell_config
}
"""

# The live shell's two writes modules/bar-clock waits for: an enable swaps a
# clonedFrom copy into the stock widget's slot (shell/services/PluginRegistry.qml:
# 529-534) and `omarchy bar set` writes one key onto a layout entry; an entry
# is a bare id or an object with one (bin/omarchy-bar:178).
ENTRY_ID = 'if type == "object" then .id else . end'
PLUGIN_ENABLE = f"""\
json="$HOME/.config/omarchy/shell.json"
src=$(jq -r '.omarchy.clonedFrom // empty' "$HOME/.config/omarchy/plugins/$1/manifest.json" 2>/dev/null) || exit 0
[[ -n $src && -f $json ]] || exit 0
jq --arg from "$src" --arg to "$1" '.bar.layout |= with_entries(.value |= map(
  if ({ENTRY_ID}) == $from then (if type == "object" then .id = $to else {{id: $to}} end) else . end))' \\
  "$json" > "$json.n" && mv "$json.n" "$json"
"""
BAR_SET = f"""\
[[ ${{1:-}} == set ]] || exit 0
json="$HOME/.config/omarchy/shell.json"; [[ -f $json ]] || exit 1
jq --arg id "$2" --arg k "$3" --arg v "$4" '.bar.layout |= with_entries(.value |= map(
  if ({ENTRY_ID}) == $id then (if type == "object" then . else {{id: .}} end) + {{($k): $v}} else . end))' \\
  "$json" > "$json.n" && mv "$json.n" "$json"
"""

# git: a clone of a LOCAL directory is real — the curl path clones the throwaway
# checkout — and a clone of a URL is modelled: the directory, a .git, and the
# pinned revision as HEAD, so modules/shell-zsh finds powerlevel10k settled on
# its pin. A pull is a no-op; nothing reaches the network or this repository.
GIT = """\
case "${1:-}" in
  clone)
    src=${@: -2:1}; dst=${@: -1}
    if [[ -d $src ]]; then exec "$(PATH=/usr/bin:/bin command -v git)" "$@"; fi
    rev=; for a in "$@"; do case $a in --revision=*) rev=${a#--revision=} ;; esac; done
    mkdir -p "$dst/.git"; printf '%s' "$rev" > "$dst/.git/head"; exit 0 ;;
  -C)
    d=$2; shift 2
    case "${1:-}" in
      rev-parse) cat "$d/.git/head" 2>/dev/null || echo unborn ;;
      fetch)     for a in "$@"; do last=$a; done; printf '%s' "$last" > "$d/.git/fetched" ;;
      checkout)  cat "$d/.git/fetched" > "$d/.git/head" 2>/dev/null ;;
    esac
    exit 0 ;;
esac
exit 0
"""


def default_app(state: Path, unset: str) -> str:
    """omarchy-default-browser / -editor: the bare call reads the default back —
    what modules/firefox and modules/vscode trust over the setter's exit status
    — and an argument sets it. `unset` is Omarchy's own answer before then."""
    return f'if (($# == 0)); then cat "{state}" 2>/dev/null || echo {unset}; else printf %s "$1" > "{state}"; fi\n'


def pin(box: Box) -> None:
    """The two root-owned paths a module writes, pinned at the box's /etc on
    every run: a run would otherwise read the developer's own /etc to decide."""
    box.env["_HYPRCONF_UDEV_RULES"] = str(box.etc / "udev/rules.d")
    box.env["_HYPRCONF_FIREFOX_POLICIES"] = str(box.etc / "firefox/policies")


def run(box: Box, *args: str, script: Path = INSTALL_SH, **kwargs) -> subprocess.CompletedProcess:
    """install.sh — or a served copy of it — against the box."""
    pin(box)
    return box.run(script, *args, **kwargs)


def run_hook(box: Box) -> subprocess.CompletedProcess:
    """The installed hook the way omarchy-hook runs it — `bash <hook>`
    (bin/omarchy-hook:26, 4.0.3-1) — with a terminal: the hook's flags, not a
    missing tty, are what keep the modules' sudo work out."""
    pin(box)
    return box.run(box.home / INSTALLED_HOOK, tty=True)


@pytest.fixture
def live(box: Box) -> Box:
    """A box every module takes its real path on: a running shell's answers,
    a sourceable shell-config, a git that settles the pin, the default-app
    setters that read back, and the shell.json a live box has — with the
    stock clock in the centre for bar-clock to swap."""
    box.stub("omarchy-hook-install", HOOK_INSTALL)
    box.stub("omarchy-shell-config", SHELL_CONFIG)
    box.stub("omarchy-plugin-enable", PLUGIN_ENABLE)
    box.stub("omarchy-bar", BAR_SET)
    # No shell answering the plugin list is what a TTY or SSH run finds
    # (omarchy-plugin-list is `set -e` over an IPC call that exits 1 the moment
    # omarchy-shell reports "is not running"), so the discovery wait is skipped.
    box.stub("omarchy-plugin-list", "exit 1\n")
    box.stub("omarchy-default-browser", default_app(box.tmp / "browser", "chromium"))
    box.stub("omarchy-default-editor", default_app(box.tmp / "editor", "nvim"))
    box.stub("git", GIT)
    shell_json = box.home / ".config/omarchy/shell.json"
    shell_json.parent.mkdir(parents=True)
    shell_json.write_text(
        json.dumps(
            {
                "version": 1,
                "bar": {
                    "centerAnchor": "omarchy.clock",
                    "layout": {
                        "left": ["omarchy.workspaces"],
                        "center": [{"id": "omarchy.clock", "format": "dddd HH:mm"}],
                        "right": [],
                    },
                },
            }
        )
    )
    return box


def tree_hash(root: Path) -> str:
    """Every path, link target and file body under root — byte-stability."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_symlink():
            h.update(b"->" + os.readlink(p).encode())
        elif p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def code_only(text: str) -> str:
    """install.sh with its comments off, so a claim about what it does cannot
    be satisfied by a comment saying so."""
    return "\n".join(
        ln.split(" #", 1)[0] for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def test_refuses_a_box_without_omarchy_before_anything_lands(box: Box) -> None:
    box.env["OMARCHY_PATH"] = str(box.tmp / "no-omarchy-here")
    proc = run(box, "--no-update")
    assert proc.returncode != 0
    assert "omarchy" in proc.stderr.lower()
    assert box.calls == [] and box.files() == set()


def test_refuses_to_run_as_root() -> None:
    """curl|bash users reflexively prefix sudo; under env_reset that
    half-installs the overlay into /root. Pinned as text, not run: the suite
    is unprivileged everywhere (CI included) and there is no seam past the
    guard — a seam was itself a way past it."""
    code = code_only(INSTALL_SH.read_text())
    assert re.search(r"^\(\(EUID\)\) \|\| die", code, re.M)
    assert "run as your regular user" in code


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------


# What a settled box's second run may still invoke: probes and writes that are
# idempotent by construction. The set-once / no-sudo gate for EVERY module at
# once — a module that re-asserted a user choice or reached for sudo on a
# re-run shows up as a name outside this set.
SETTLED_RERUN_COMMANDS = {
    "omarchy-hook-install",  # Omarchy's own mkdir/cp/chmod, the same bytes every time
    "omarchy-pkg-present",  # every module's `pacman -Q` probe
    # The bar modules' folders are symlinks, which the shell's inotifywait -r
    # never descends (PluginRegistry.qml:663-667): the rescan repeats on every
    # run by design, and is pure IPC.
    "omarchy-shell",
    "git",  # modules/shell-zsh reading powerlevel10k's HEAD against its pin
}


def test_a_full_run_reaches_every_module_and_a_second_run_is_byte_stable(live: Box) -> None:
    """Every module on its real path — a sudo that runs its command lands the
    two root writes in the box's /etc — then a second run that changes not a
    byte of HOME or /etc, warns about nothing, and calls nothing outside
    SETTLED_RERUN_COMMANDS. The modules are held to their own suites; the
    spot checks here only prove the fakes let each of them get that far."""
    live.stub("sudo", '"$@"\n')
    first = run(live, "--no-update", tty=True)
    assert first.returncode == 0, first.stderr
    assert sorted(ran(first)) == modules()
    home = live.home
    assert (live.etc / "firefox/policies/policies.json").is_file()
    assert (live.etc / "udev/rules.d/70-keychron.rules").is_file()
    bindings = home / ".config/hypr/bindings.lua"
    assert not bindings.is_symlink()
    assert bindings.read_bytes() == (MODULES / "hypr/bindings.lua").read_bytes()
    assert "source" in (home / ".zshrc").read_text()
    for name in ("clock", "active-window", "resources", "workspaces"):
        link = home / ".config/omarchy/plugins" / f"hyprconf.{name}"
        assert link.is_symlink() and Path(os.readlink(link)) == MODULES / f"bar-{name}/plugin"
    state = home / ".local/state/hyprconf"
    for marker in ("clock", "idle", "font", "editor", "browser", "terminal"):
        assert (state / f"{marker}-applied").exists(), marker
    shell = json.loads((home / ".config/omarchy/shell.json").read_text())
    assert shell["bar"]["centerAnchor"] == "hyprconf.clock"  # the swap, followed
    assert shell["idle"]["screensaver"] == 900
    assert Path(os.readlink(home / LINK)) == INSTALL_SH
    assert (home / INSTALLED_HOOK).read_bytes() == HOOK.read_bytes()

    after = (tree_hash(home), tree_hash(live.etc))
    live.reset()
    second = run(live, "--no-update", tty=True)
    assert second.returncode == 0, second.stderr
    assert (tree_hash(home), tree_hash(live.etc)) == after
    assert "WARNING" not in second.stderr, second.stderr
    assert set(live.commands) <= SETTLED_RERUN_COMMANDS, set(live.commands)
    for forbidden in ("omarchy-theme-set", "omarchy-pkg-drop", "pacman", "chsh"):
        assert forbidden not in live.commands, forbidden


@pytest.mark.parametrize(
    "order",
    [("shell-zsh", "terminal-kitty"), ("terminal-kitty", "shell-zsh")],
    ids=["loop-order", "reversed"],
)
def test_the_two_kitty_includes_are_order_free(box: Box, order: tuple[str, str]) -> None:
    """The loop is alphabetical, so shell-zsh runs BEFORE terminal-kitty — and
    both write ~/.config/kitty/kitty.conf. Neither may depend on that: both
    seed an absent file from Omarchy's own stub (the theme include lives only
    there, config/kitty/kitty.conf:1-2) and both guard only their own line, so
    either order ends with the stub plus exactly one of each include — and
    undoing both puts Omarchy's stub back byte for byte."""
    conf = box.home / ".config" / "kitty" / "kitty.conf"
    stub = (box.omarchy / "config" / "kitty" / "kitty.conf").read_text()

    for _ in range(2):  # and a re-run of either adds nothing
        for name in order:
            proc = box.run(MODULES / name / "install")
            assert proc.returncode == 0, f"{name}: {proc.stderr}"

    text = conf.read_text()
    assert text.startswith(stub), text
    assert sorted(text[len(stub) :].splitlines()) == [
        "# hyprconf overlay",
        "include hyprconf-zsh.conf",
        "include hyprconf.conf",
    ], text

    for name in reversed(order):
        assert box.undo(name).returncode == 0
    assert conf.read_text() == stub


# ---------------------------------------------------------------------------
# Flags and module selection
# ---------------------------------------------------------------------------


def test_sync_pulls_applies_then_runs_omarchy_update(box: Box) -> None:
    """--sync is pull, apply, omarchy-update, in that order — Omarchy's own
    updater, never pacman — with the pull pinned to `--ff-only` under
    `pull.rebase=false` (install.sh says why)."""
    proc = run(box, "--sync", "fastfetch")
    assert proc.returncode == 0, proc.stderr
    assert box.calls_of("git") == [
        ["git", "-C", str(REPO_ROOT), "-c", "pull.rebase=false", "pull", "--ff-only"]
    ]
    names = box.commands
    assert names.index("git") < names.index("omarchy-hook-install") < names.index("omarchy-update")
    assert "pacman" not in names


@pytest.mark.parametrize("order", [("--no-update", "--sync"), ("--sync", "--no-update")])
def test_no_update_beats_sync_in_either_order(box: Box, order: tuple[str, str]) -> None:
    proc = run(box, *order, "fastfetch")
    assert proc.returncode == 0, proc.stderr
    assert "git" in box.commands  # pulled and applied
    assert "omarchy-update" not in box.commands  # never updated


def test_a_failed_pull_stops_the_sync_before_anything_is_applied(box: Box) -> None:
    """A pull that fails is a stop with git's own error above it — never a
    stale checkout applied and an Omarchy update run on top of it."""
    box.stub("git", 'case " $* " in *" pull "*) exit 1 ;; esac; exit 0\n')
    proc = run(box, "--sync")
    assert proc.returncode != 0
    assert "git pull failed" in proc.stderr
    assert box.commands == ["git"]
    assert box.files() == set()


def test_an_unknown_option_is_refused_before_anything_runs(box: Box) -> None:
    proc = run(box, "--definitely-not-a-flag")
    assert proc.returncode != 0
    assert "unknown option" in proc.stderr
    assert box.calls == [] and box.files() == set()


def test_help_is_the_contract(box: Box) -> None:
    """-h names both forms, every flag and the three variables, and touches
    nothing — on the curl path it answers from the served copy."""
    proc = run(box, "--help")
    assert proc.returncode == 0
    for token in (
        ONE_LINER,
        "hyprconf [OPTIONS] [MODULE...]",
        "--sync",
        "--no-update",
        "--no-packages",
        "--undo",
        "HYPRCONF_REPO",
        "HYPRCONF_BRANCH",
        "HYPRCONF_DIR",
    ):
        assert token in proc.stdout, token
    assert box.calls == [] and box.files() == set()


def test_a_module_named_on_the_command_line_runs_alone(box: Box) -> None:
    """`hyprconf hypr` is the re-apply after an edit: only the modules named
    run, plus the link and the hook, both idempotent."""
    proc = run(box, "--no-update", "hypr")
    assert proc.returncode == 0, proc.stderr
    assert ran(proc) == ["hypr"]
    bindings = box.home / ".config/hypr/bindings.lua"
    assert bindings.read_bytes() == (MODULES / "hypr/bindings.lua").read_bytes()
    assert set(box.commands) == {"hyprctl", "omarchy-hook-install"}, box.commands
    assert not (box.home / ".zshrc").exists()  # modules/shell-zsh did not run


def test_a_name_that_is_no_module_dies_before_anything_runs(box: Box) -> None:
    proc = run(box, "--no-update", "hypr", "no-such-module")
    assert proc.returncode != 0
    assert "no module named no-such-module" in proc.stderr
    assert box.calls == [] and box.files() == set()


def test_a_failing_module_is_named_and_stops_the_update(box: Box, tmp_path: Path) -> None:
    """One module's failure is its own: the rest still run, the hook is still
    installed, the run ends non-zero naming the module — and under --sync
    omarchy-update is not run on top of it."""
    (box.home / ".config").mkdir()
    (box.home / ".config/hyprconf").write_text("a file where modules/fastfetch needs a directory\n")
    proc = run(box, "--sync", "fastfetch", "hypr")
    assert proc.returncode != 0, proc.stdout
    assert "failed: fastfetch" in proc.stderr
    assert ran(proc) == ["fastfetch", "hypr"]
    assert (box.home / ".config/hypr/bindings.lua").is_file()  # hypr still ran
    assert "omarchy-hook-install" in box.commands
    assert "omarchy-update" not in box.commands


# ---------------------------------------------------------------------------
# The link and the hook
# ---------------------------------------------------------------------------


def test_the_installer_lands_on_path_as_hyprconf_and_is_never_re_linked(box: Box) -> None:
    """`hyprconf --sync` is what modules/shell-zsh's `hyprsync` alias runs,
    `hyprconf <module>` the re-apply, and the hook execs it. A SYMLINK — a
    `git pull` is the update, and the alias names the link, not the checkout
    — re-pointed only when wrong, so a re-run does not even recreate it."""
    assert run(box, "--no-update", "fastfetch").returncode == 0
    link = box.home / LINK
    assert link.is_symlink() and Path(os.readlink(link)) == INSTALL_SH
    before = link.lstat().st_ino
    assert run(box, "--no-update", "fastfetch").returncode == 0
    assert link.lstat().st_ino == before


def test_the_hook_is_installed_through_omarchy_hook_install_unrendered(box: Box) -> None:
    """One `omarchy-hook-install post-update hooks/10-hyprconf` per run
    (Omarchy's own mkdir/cp/chmod 755, bin/omarchy-hook-install:27-29). The
    copy is the shipped file byte for byte: no checkout path is rendered into
    it, because it runs the link."""
    box.stub("omarchy-hook-install", HOOK_INSTALL)
    assert run(box, "--no-update", "fastfetch").returncode == 0
    assert box.calls_of("omarchy-hook-install") == [
        ["omarchy-hook-install", "post-update", str(HOOK)]
    ]
    installed = box.home / INSTALLED_HOOK
    assert installed.read_bytes() == HOOK.read_bytes()
    assert os.access(installed, os.X_OK)
    assert str(REPO_ROOT) not in installed.read_text()


def test_the_post_update_hook_reapplies_through_the_link_without_update_or_sudo(live: Box) -> None:
    """omarchy-update runs the migrations and THEN this hook
    (bin/omarchy-update:48-49), which execs ~/.local/bin/hyprconf with
    `--no-update --no-packages` — the recursion guard and the production path
    of both flags: the whole loop runs, and nothing that needs sudo does."""
    live.stub("omarchy-pkg-present", "exit 1\n")  # nothing installed: everything a sudo would fetch
    assert run(live, "--no-update").returncode == 0
    bindings = live.home / ".config/hypr/bindings.lua"
    bindings.write_text("-- a migration put the stock file back\n")
    live.reset()
    proc = run_hook(live)
    assert proc.returncode == 0, proc.stderr
    assert sorted(ran(proc)) == modules()
    assert bindings.read_bytes() == (MODULES / "hypr/bindings.lua").read_bytes()
    for forbidden in (
        "omarchy-update",
        "sudo",
        "omarchy-pkg-add",
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
        "udevadm",
    ):
        assert forbidden not in live.commands, forbidden


def test_the_hook_bows_out_when_the_link_is_gone(live: Box) -> None:
    """A moved or deleted checkout leaves the link dangling: the hook says so
    on stderr and exits 0 — omarchy-hook reports a failing hook
    (bin/omarchy-hook:26), and an update must never look failed over a
    missing overlay. Nothing runs."""
    assert run(live, "--no-update", "fastfetch").returncode == 0
    link = live.home / LINK
    link.unlink()
    link.symlink_to(live.tmp / "moved-away" / "install.sh")
    live.reset()
    proc = run_hook(live)
    assert proc.returncode == 0, proc.stderr
    assert "gone" in proc.stderr
    assert live.calls == []


# ---------------------------------------------------------------------------
# --undo
# ---------------------------------------------------------------------------


def test_undo_runs_every_module_in_reverse_then_removes_the_hook_and_the_link(live: Box) -> None:
    live.stub("sudo", '"$@"\n')
    applied = run(live, "--no-update", tty=True)
    assert applied.returncode == 0
    live.reset()
    proc = run(live, "--undo", tty=True)
    assert proc.returncode == 0, proc.stderr
    assert undone(proc) == ran(applied)[::-1]
    home = live.home
    assert not (home / INSTALLED_HOOK).exists()
    assert not (home / LINK).is_symlink()
    assert not list((home / ".local/state/hyprconf").glob("*-applied"))
    assert not list((home / ".config/omarchy/plugins").glob("hyprconf.*"))
    assert not (live.etc / "firefox/policies/policies.json").exists()
    assert not (live.etc / "udev/rules.d/70-keychron.rules").exists()
    assert "source" not in (home / ".zshrc").read_text() if (home / ".zshrc").exists() else True
    assert "omarchy-update" not in live.commands


def test_undo_of_named_modules_keeps_the_hook_and_the_link(live: Box) -> None:
    assert run(live, "--no-update").returncode == 0
    live.reset()
    proc = run(live, "--undo", "hypr", "fastfetch")
    assert proc.returncode == 0, proc.stderr
    assert undone(proc) == ["fastfetch", "hypr"]
    assert (live.home / INSTALLED_HOOK).exists()
    assert (live.home / LINK).is_symlink()
    assert not (live.home / ".config/hyprconf/fastfetch.jsonc").exists()
    assert (live.home / ".zshrc").exists()  # modules/shell-zsh was left alone


def test_a_failing_undo_does_not_stop_the_others(live: Box) -> None:
    applied = run(live, "--no-update")
    assert applied.returncode == 0
    live.stub("omarchy-refresh-config", "exit 1\n")  # modules/hypr's undo dies on it
    live.reset()
    proc = run(live, "--undo")
    assert proc.returncode != 0
    assert "undo failed: hypr" in proc.stderr
    assert undone(proc) == ran(applied)[::-1]
    assert not (live.home / INSTALLED_HOOK).exists()
    assert not (live.home / LINK).is_symlink()


# ---------------------------------------------------------------------------
# The curl path — hyprconf.sh serves install.sh alone
# ---------------------------------------------------------------------------

PAYLOAD = ("install.sh", "modules", "hooks")


def checkout(tmp: Path) -> Path:
    """A throwaway git checkout of the payload on `stable` — what the curl
    path clones and runs from, never the repository the suite runs in."""
    repo = tmp / "checkout"
    repo.mkdir()
    for name in PAYLOAD:
        src = REPO_ROOT / name
        if src.is_dir():
            shutil.copytree(src, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, repo / name)
    git(repo, "init", "-q", "-b", "stable")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "payload")
    return repo


def served(tmp: Path) -> Path:
    """install.sh alone, the way hyprconf.sh serves it: no payload beside it."""
    (tmp / "served").mkdir()
    return Path(shutil.copy2(INSTALL_SH, tmp / "served" / "install.sh"))


def test_the_curl_path_clones_the_checkout_and_hands_over_to_it(live: Box, tmp_path: Path) -> None:
    """With nothing beside it, install.sh clones HYPRCONF_REPO (branch stable,
    single-branch) into HYPRCONF_DIR and execs that checkout's copy with the
    same arguments — which then runs every module from the checkout."""
    repo = checkout(tmp_path)
    target = tmp_path / "hyprconf-dir"
    live.env.update({"HYPRCONF_REPO": str(repo), "HYPRCONF_DIR": str(target)})
    proc = run(live, "--no-update", script=served(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert live.calls_of("git")[0] == [
        "git",
        "clone",
        "--branch",
        "stable",
        "--single-branch",
        "--",
        str(repo),
        str(target),
    ]
    assert (target / ".git").is_dir()
    assert sorted(ran(proc)) == modules()
    home = live.home
    assert Path(os.readlink(home / LINK)) == target / "install.sh"
    assert (home / INSTALLED_HOOK).read_bytes() == (target / "hooks/10-hyprconf").read_bytes()
    bindings = home / ".config/hypr/bindings.lua"
    assert bindings.read_bytes() == (target / "modules/hypr/bindings.lua").read_bytes()
    gaps = home / ".local/bin/hyprconf-gaps"
    assert Path(os.readlink(gaps)) == target / "modules/hypr/bin/hyprconf-gaps"
    assert "omarchy-update" not in live.commands


def test_the_curl_path_refuses_a_box_without_omarchy_before_cloning(
    box: Box, tmp_path: Path
) -> None:
    target = tmp_path / "hyprconf-dir"
    box.env.update({"OMARCHY_PATH": str(tmp_path / "no-omarchy-here"), "HYPRCONF_DIR": str(target)})
    proc = run(box, script=served(tmp_path))
    assert proc.returncode != 0
    assert "omarchy" in proc.stderr.lower()
    assert not target.exists()
    assert box.calls == [] and box.files() == set()


def test_the_curl_path_reuses_an_existing_checkout_without_pulling(
    live: Box, tmp_path: Path
) -> None:
    """A checkout already at HYPRCONF_DIR is used as it is: no clone over it,
    no pull either — updating it is --sync's job, not the bootstrap's."""
    repo = checkout(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    live.env.update({"HYPRCONF_REPO": str(tmp_path / "never-cloned"), "HYPRCONF_DIR": str(repo)})
    proc = run(live, "--no-update", script=served(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert not any(c[1] == "clone" and c[-1] == str(repo) for c in live.calls_of("git"))
    assert not any("pull" in c for c in live.calls_of("git"))
    assert not (tmp_path / "never-cloned").exists()
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain") == ""
    assert Path(os.readlink(live.home / LINK)) == repo / "install.sh"


def test_the_curl_path_answers_help_and_refuses_a_typo_without_cloning(
    box: Box, tmp_path: Path
) -> None:
    target = tmp_path / "hyprconf-dir"
    box.env["HYPRCONF_DIR"] = str(target)
    copy = served(tmp_path)
    proc = run(box, "--help", script=copy)
    assert proc.returncode == 0 and ONE_LINER in proc.stdout
    proc = run(box, "--bogus", script=copy)
    assert proc.returncode != 0
    assert not target.exists()
    assert box.calls == []


# ---------------------------------------------------------------------------
# Restraint — across the whole run
# ---------------------------------------------------------------------------


def test_install_sh_itself_names_no_sudo_and_never_switches_the_theme() -> None:
    """The core asks for no sudo — every root write is a module's, behind its
    own gate — and never takes the active theme (modules/themes links its
    theme and never activates it). Scanned, so every branch is covered."""
    code = code_only(INSTALL_SH.read_text())
    assert "omarchy-theme-set" not in re.findall(r"\bomarchy-[a-z0-9-]+\b", code)
    # What runs: the usage heredoc and the messages name sudo, as prose.
    bare = re.sub(
        r'"(?:\\.|[^"\\])*"', '""', re.sub(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$", "", code)
    )
    for word in ("sudo", "pacman", "chsh"):
        assert not re.search(rf"\b{word}\b", bare), word


@pytest.mark.parametrize("gate", ["no-terminal", "no-packages"])
def test_every_sudo_gate_holds_across_a_whole_run(live: Box, gate: str) -> None:
    """The one place every module's gate is held to in a single run, with
    everything absent that a sudo would install: no terminal for the prompt,
    and the hook's --no-packages with one. Nothing sudo, nothing installed,
    no policy written — and the run still succeeds."""
    live.stub("omarchy-pkg-present", "exit 1\n")
    args = ("--no-update",) if gate == "no-terminal" else ("--no-update", "--no-packages")
    proc = run(live, *args, tty=gate == "no-packages")
    assert proc.returncode == 0, proc.stderr
    assert sorted(ran(proc)) == modules()
    for forbidden in (
        "sudo",
        "udevadm",
        "omarchy-pkg-add",
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
    ):
        assert forbidden not in live.commands, forbidden
    assert not (live.etc / "firefox/policies/policies.json").exists()
