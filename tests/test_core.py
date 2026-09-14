"""install.sh, the core: the curl bootstrap, the flags, the module loop, the
~/.local/bin/hyprconf link, the post-update hook, --undo, and the restraint a whole run
is held to (AGENTS.md rule 6). Each module's behaviour is its own suite's."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (
    BAR_SET,
    GIT_FAKE,
    HOOK_INSTALL,
    PLUGIN_ENABLE,
    SHELL_CONFIG,
    SUDO_RUNS,
    Box,
    default_app,
    git,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "install.sh"
MODULES = REPO_ROOT / "modules"
HOOK = REPO_ROOT / "hooks" / "10-hyprconf"
INSTALLED_HOOK = ".config/omarchy/hooks/post-update.d/10-hyprconf"
LINK = ".local/bin/hyprconf"
BINDINGS = ".config/hypr/bindings.lua"
POLICY, RULE = "firefox/policies/policies.json", "udev/rules.d/70-keychron.rules"
# What a settled box's second run may still call, idempotent by construction: a module
# that re-asserted a choice or reached for sudo on a re-run is a name outside this set.
SETTLED_RERUN_COMMANDS = {"omarchy-hook-install", "omarchy-pkg-present", "omarchy-shell", "git"}
# What no run without a terminal or with --no-packages may call.
SUDO_WORK = {
    "sudo",
    "udevadm",
    "omarchy-pkg-add",
    "omarchy-install-browser",
    "omarchy-install-editor-vscode",
}


def modules() -> list[str]:
    return sorted(p.parent.name for p in MODULES.glob("*/install"))


def ran(proc: subprocess.CompletedProcess) -> list[str]:
    """The module names the core announced (`==> <name>`), in order."""
    return [m for m in re.findall(r"^==> (\S+)$", proc.stdout, re.M) if m in modules()]


def undone(proc: subprocess.CompletedProcess) -> list[str]:
    return re.findall(r"^==> undo (\S+)$", proc.stdout, re.M)


def served(tmp: Path) -> Path:
    """install.sh alone, the way hyprconf.sh serves it: no payload beside it."""
    (tmp / "served").mkdir()
    return Path(shutil.copy2(INSTALL_SH, tmp / "served" / "install.sh"))


def checkout(tmp: Path) -> Path:
    """A throwaway git checkout of the payload on `stable`, for the curl path to clone."""
    repo = tmp / "checkout"
    repo.mkdir()
    for name in ("install.sh", "modules", "hooks"):
        src = REPO_ROOT / name
        if src.is_dir():
            shutil.copytree(src, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, repo / name)
    git(repo, "init", "-q", "-b", "stable")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "payload")
    return repo


def hook(box: Box) -> subprocess.CompletedProcess:
    """The installed hook as omarchy-hook runs it, `bash <hook>` (bin/omarchy-hook:26), on a tty."""
    return box.run(box.home / INSTALLED_HOOK, tty=True)


def code_only(text: str) -> str:
    lines = (ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    return "\n".join(ln.split(" #", 1)[0] for ln in lines)


@pytest.fixture
def live(box: Box) -> Box:
    """A box every module takes its real path on: the shell's writes, a sourceable
    shell-config, a git that settles the pin, default-app setters that read back, and a
    shell.json with the stock clock in the centre for bar-clock to swap."""
    box.stub("omarchy-hook-install", HOOK_INSTALL)
    box.stub("omarchy-shell-config", SHELL_CONFIG)
    box.stub("omarchy-plugin-enable", PLUGIN_ENABLE)
    box.stub("omarchy-bar", BAR_SET)
    box.stub("omarchy-plugin-list", "exit 1\n")  # no running shell: the discovery wait is skipped
    box.stub("omarchy-default-browser", default_app(box.tmp / "browser", "chromium"))
    box.stub("omarchy-default-editor", default_app(box.tmp / "editor", "nvim"))
    box.stub("git", GIT_FAKE)
    shell_json = box.home / ".config/omarchy/shell.json"
    shell_json.parent.mkdir(parents=True)
    center = [{"id": "omarchy.clock", "format": "dddd HH:mm"}]
    layout = {"left": ["omarchy.workspaces"], "center": center, "right": []}
    bar = {"centerAnchor": "omarchy.clock", "layout": layout}
    shell_json.write_text(json.dumps({"version": 1, "bar": bar}))
    return box


def test_refuses_a_box_without_omarchy_before_anything_lands(box: Box, tmp_path: Path) -> None:
    """On the served copy: the preflight comes before the clone."""
    target = tmp_path / "hyprconf-dir"
    box.env.update({"OMARCHY_PATH": str(tmp_path / "no-omarchy-here"), "HYPRCONF_DIR": str(target)})
    proc = box.run(served(tmp_path), "--no-update")
    assert proc.returncode != 0 and "omarchy" in proc.stderr.lower()
    assert not target.exists() and box.calls == [] and box.files() == set()


def test_refuses_to_run_as_root() -> None:
    """Pinned as text: the suite is unprivileged everywhere, and a seam past the guard
    would itself be a way past it."""
    assert re.search(r"^\(\(EUID\)\) \|\| die", code_only(INSTALL_SH.read_text()), re.M)


def test_a_full_run_reaches_every_module_and_a_second_run_is_byte_stable(live: Box) -> None:
    live.stub("sudo", SUDO_RUNS)
    first = live.core("--no-update", tty=True)
    assert first.returncode == 0, first.stderr
    assert sorted(ran(first)) == modules()
    assert not {"omarchy-theme-set", "omarchy-pkg-drop"} & set(live.commands)
    home = live.home
    assert (live.etc / POLICY).is_file() and (live.etc / RULE).is_file()
    assert not (home / BINDINGS).is_symlink()
    assert (home / BINDINGS).read_bytes() == (MODULES / "hypr/bindings.lua").read_bytes()
    assert "source" in (home / ".zshrc").read_text()
    for name in ("clock", "active-window", "resources", "workspaces"):
        link = home / ".config/omarchy/plugins" / f"hyprconf.{name}"
        assert link.is_symlink() and Path(os.readlink(link)) == MODULES / f"bar-{name}/plugin"
    for marker in ("clock", "idle", "font", "editor", "browser", "terminal"):
        assert (home / ".local/state/hyprconf" / f"{marker}-applied").exists(), marker
    shell = json.loads((home / ".config/omarchy/shell.json").read_text())
    assert shell["bar"]["centerAnchor"] == "hyprconf.clock" and shell["idle"]["screensaver"] == 900
    assert Path(os.readlink(home / LINK)) == INSTALL_SH
    assert (home / INSTALLED_HOOK).read_bytes() == HOOK.read_bytes()

    settled = live.snapshot()
    live.reset()
    second = live.core("--no-update", tty=True)
    assert second.returncode == 0, second.stderr
    after = live.snapshot()
    # Omarchy's own cp rewrites the hook's bytes each run (bin/omarchy-hook-install:28).
    assert after.pop(f"home/{INSTALLED_HOOK}")[3] == settled.pop(f"home/{INSTALLED_HOOK}")[3]
    assert after == settled
    assert "WARNING" not in second.stderr, second.stderr
    assert set(live.commands) <= SETTLED_RERUN_COMMANDS, set(live.commands)


# bin/omarchy-font-set:33-40, the kitty half: with kitty on PATH it CREATES an absent
# user file, holding nothing but font_family.
FONT_SET = (
    "if [[ -f ~/.config/kitty/kitty.conf ]] || omarchy-cmd-present kitty; then\n"
    "  mkdir -p ~/.config/kitty\n"
    "  if grep -qE '^[[:space:]]*font_family[[:space:]]+' ~/.config/kitty/kitty.conf 2>/dev/null; then\n"
    '    sed --follow-symlinks -i -E "s/^[[:space:]]*font_family[[:space:]]+.*/font_family $1/" ~/.config/kitty/kitty.conf\n'
    "  else\n"
    "    printf '\\nfont_family %s\\n' \"$1\" >>~/.config/kitty/kitty.conf\n"
    "  fi\n"
    "fi\n"
)
KITTY_WRITERS = ("font", "shell-zsh", "terminal-kitty")


@pytest.mark.parametrize("order", [KITTY_WRITERS, KITTY_WRITERS[::-1]], ids=["loop", "reversed"])
def test_the_kitty_conf_writers_are_order_free(box: Box, order: tuple[str, ...]) -> None:
    """Three modules write ~/.config/kitty/kitty.conf and none may depend on the loop's
    order: every order ends with Omarchy's stub, the font line and one of each include,
    and undoing the two kitty modules leaves the stub plus the setter's line."""
    box.stub("omarchy-font-set", FONT_SET)
    conf = box.home / ".config" / "kitty" / "kitty.conf"
    stub = (box.omarchy / "config" / "kitty" / "kitty.conf").read_text()
    for _ in range(2):
        for name in order:
            proc = box.run(MODULES / name / "install")
            assert proc.returncode == 0, f"{name}: {proc.stderr}"
    text = conf.read_text()
    assert text.startswith(stub), text
    assert sorted(text[len(stub) :].splitlines()) == [
        "",
        "# hyprconf overlay",
        "font_family GeistMono Nerd Font",
        "include hyprconf-zsh.conf",
        "include hyprconf.conf",
    ], text
    for name in reversed(order):
        assert box.undo(name).returncode == 0
    assert conf.read_text() == stub + "\nfont_family GeistMono Nerd Font\n"


def test_sync_pulls_applies_then_runs_omarchy_update(box: Box) -> None:
    """Pull (--ff-only under pull.rebase=false), apply, omarchy-update, in that order; a
    failed pull is a stop before anything is applied."""
    box.stub("git", 'case " $* " in *" pull "*) exit 1 ;; esac; exit 0\n')
    proc = box.core("--sync")
    assert proc.returncode != 0 and "git pull failed" in proc.stderr
    assert box.commands == ["git"] and box.files() == set()
    box.stub("git")
    box.reset()
    proc = box.core("--sync", "fastfetch")
    assert proc.returncode == 0, proc.stderr
    pull = ["git", "-C", str(REPO_ROOT), "-c", "pull.rebase=false", "pull", "--ff-only"]
    assert box.calls_of("git") == [pull]
    names = box.commands
    assert names.index("git") < names.index("omarchy-hook-install") < names.index("omarchy-update")


def test_no_update_beats_sync(box: Box) -> None:
    proc = box.core("--sync", "--no-update", "fastfetch")
    assert proc.returncode == 0, proc.stderr
    assert "git" in box.commands and "omarchy-update" not in box.commands


def test_help_names_every_flag_and_touches_nothing(box: Box, tmp_path: Path) -> None:
    box.env["HYPRCONF_DIR"] = str(tmp_path / "hyprconf-dir")
    proc = box.run(served(tmp_path), "--help")
    assert proc.returncode == 0 and proc.stdout.startswith("Usage:")
    assert all(f in proc.stdout for f in ("--sync", "--no-update", "--no-packages", "--undo"))
    assert not (tmp_path / "hyprconf-dir").exists() and box.calls == [] and box.files() == set()


def test_an_unknown_option_is_refused_before_anything_runs(box: Box, tmp_path: Path) -> None:
    box.env["HYPRCONF_DIR"] = str(tmp_path / "hyprconf-dir")
    proc = box.run(served(tmp_path), "--definitely-not-a-flag")
    assert proc.returncode != 0 and "unknown option" in proc.stderr
    assert not (tmp_path / "hyprconf-dir").exists() and box.calls == [] and box.files() == set()


def test_named_modules_run_alone_and_an_unknown_name_dies_first(box: Box) -> None:
    proc = box.core("--no-update", "hypr", "no-such-module")
    assert proc.returncode != 0 and "no module named no-such-module" in proc.stderr
    assert box.calls == [] and box.files() == set()
    proc = box.core("--no-update", "hypr")
    assert proc.returncode == 0, proc.stderr
    assert ran(proc) == ["hypr"]
    assert (box.home / BINDINGS).read_bytes() == (MODULES / "hypr/bindings.lua").read_bytes()
    assert set(box.commands) == {"hyprctl", "omarchy-hook-install"}, box.commands
    assert not (box.home / ".zshrc").exists()


def test_a_failing_module_is_named_and_stops_the_update(box: Box) -> None:
    (box.home / ".config").mkdir()
    (box.home / ".config/hyprconf").write_text("a file where modules/fastfetch needs a directory\n")
    proc = box.core("--sync", "fastfetch", "hypr")
    assert proc.returncode != 0 and "failed: fastfetch" in proc.stderr
    assert ran(proc) == ["fastfetch", "hypr"] and (box.home / BINDINGS).is_file()
    assert "omarchy-hook-install" in box.commands and "omarchy-update" not in box.commands


def test_the_hook_is_installed_unrendered_and_reapplies_through_the_link(live: Box) -> None:
    """omarchy-hook-install copies the shipped file byte for byte (no checkout path: it
    runs the link); omarchy-update runs it after the migrations (bin/omarchy-update:48-49)
    and it execs the link with --no-update --no-packages: the whole loop, no sudo work."""
    live.stub("omarchy-pkg-present", "exit 1\n")
    assert live.core("--no-update").returncode == 0
    installs = [c for c in live.calls_of("omarchy-hook-install") if c[1] == "post-update"]
    assert installs == [["omarchy-hook-install", "post-update", str(HOOK)]]
    installed = live.home / INSTALLED_HOOK
    assert installed.read_bytes() == HOOK.read_bytes() and os.access(installed, os.X_OK)
    assert str(REPO_ROOT) not in installed.read_text()
    bindings = live.home / BINDINGS
    bindings.write_text("-- a migration put the stock file back\n")
    live.reset()
    proc = hook(live)
    assert proc.returncode == 0, proc.stderr
    assert sorted(ran(proc)) == modules()
    assert bindings.read_bytes() == (MODULES / "hypr/bindings.lua").read_bytes()
    assert not (SUDO_WORK | {"omarchy-update"}) & set(live.commands), live.commands


def test_the_hook_bows_out_when_the_link_is_gone(live: Box) -> None:
    """omarchy-hook reports a failing hook (bin/omarchy-hook:26): a missing overlay says
    so on stderr and exits 0."""
    assert live.core("--no-update", "fastfetch").returncode == 0
    link = live.home / LINK
    link.unlink()
    link.symlink_to(live.tmp / "moved-away" / "install.sh")
    live.reset()
    proc = hook(live)
    assert proc.returncode == 0 and "gone" in proc.stderr and live.calls == []


def test_undo_runs_every_module_in_reverse_then_removes_the_hook_and_the_link(live: Box) -> None:
    live.stub("sudo", SUDO_RUNS)
    applied = live.core("--no-update", tty=True)
    assert applied.returncode == 0
    live.reset()
    proc = live.core("--undo", tty=True)
    assert proc.returncode == 0, proc.stderr
    assert undone(proc) == ran(applied)[::-1]
    home = live.home
    assert not (home / INSTALLED_HOOK).exists() and not (home / LINK).is_symlink()
    assert not list((home / ".local/state/hyprconf").glob("*-applied"))
    assert not list((home / ".config/omarchy/plugins").glob("hyprconf.*"))
    assert not (live.etc / POLICY).exists() and not (live.etc / RULE).exists()
    zshrc = home / ".zshrc"
    assert not zshrc.exists() or "source" not in zshrc.read_text()
    assert "omarchy-update" not in live.commands


def test_undo_of_named_modules_keeps_the_hook_and_the_link(live: Box) -> None:
    assert live.core("--no-update").returncode == 0
    live.reset()
    proc = live.core("--undo", "hypr", "fastfetch")
    assert proc.returncode == 0, proc.stderr
    assert undone(proc) == ["fastfetch", "hypr"]
    assert (live.home / INSTALLED_HOOK).exists() and (live.home / LINK).is_symlink()
    assert not (live.home / ".config/hyprconf/fastfetch.jsonc").exists()
    assert (live.home / ".zshrc").exists()


def test_a_failing_undo_does_not_stop_the_others(live: Box) -> None:
    applied = live.core("--no-update")
    assert applied.returncode == 0
    live.stub("omarchy-refresh-config", "exit 1\n")  # modules/hypr's undo dies on it
    live.reset()
    proc = live.core("--undo")
    assert proc.returncode != 0 and "undo failed: hypr" in proc.stderr
    assert undone(proc) == ran(applied)[::-1]
    assert not (live.home / INSTALLED_HOOK).exists() and not (live.home / LINK).is_symlink()


def test_the_curl_path_clones_the_checkout_and_hands_over_to_it(live: Box, tmp_path: Path) -> None:
    repo, target = checkout(tmp_path), tmp_path / "hyprconf-dir"
    live.env.update({"HYPRCONF_REPO": str(repo), "HYPRCONF_DIR": str(target)})
    proc = live.run(served(tmp_path), "--no-update")
    assert proc.returncode == 0, proc.stderr
    clone = ["git", "clone", "--branch", "stable", "--single-branch", "--", str(repo), str(target)]
    assert live.calls_of("git")[0] == clone
    assert (target / ".git").is_dir() and sorted(ran(proc)) == modules()
    home = live.home
    assert Path(os.readlink(home / LINK)) == target / "install.sh"
    assert (home / INSTALLED_HOOK).read_bytes() == (target / "hooks/10-hyprconf").read_bytes()
    assert (home / BINDINGS).read_bytes() == (target / "modules/hypr/bindings.lua").read_bytes()
    gaps = home / ".local/bin/hyprconf-gaps"
    assert Path(os.readlink(gaps)) == target / "modules/hypr/bin/hyprconf-gaps"
    assert "omarchy-update" not in live.commands


def test_the_curl_path_reuses_a_checkout_without_pulling(live: Box, tmp_path: Path) -> None:
    repo = checkout(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    live.env.update({"HYPRCONF_REPO": str(tmp_path / "never-cloned"), "HYPRCONF_DIR": str(repo)})
    proc = live.run(served(tmp_path), "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not any(c[1] == "clone" and c[-1] == str(repo) for c in live.calls_of("git"))
    assert not any("pull" in c for c in live.calls_of("git"))
    assert not (tmp_path / "never-cloned").exists()
    assert git(repo, "rev-parse", "HEAD") == head and git(repo, "status", "--porcelain") == ""
    assert Path(os.readlink(live.home / LINK)) == repo / "install.sh"


def test_install_sh_itself_names_no_sudo_and_never_switches_the_theme() -> None:
    """Scanned, so every branch is covered: every root write is a module's, behind its own
    gate (test_scans.py holds the pacman / AUR / chsh rule over every script)."""
    code = re.sub(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$", "", code_only(INSTALL_SH.read_text()))
    assert "omarchy-theme-set" not in code
    assert not re.search(r"\bsudo\b", re.sub(r'"(?:\\.|[^"\\])*"', '""', code))


@pytest.mark.parametrize("gate", ["no-terminal", "no-packages"])
def test_every_sudo_gate_holds_across_a_whole_run(live: Box, gate: str) -> None:
    """Every module's gate in one run, with everything absent that a sudo would install:
    no terminal, and the hook's --no-packages with one. Nothing sudo, nothing installed,
    no policy written, and the run still succeeds."""
    live.stub("omarchy-pkg-present", "exit 1\n")
    args = ("--no-update",) if gate == "no-terminal" else ("--no-update", "--no-packages")
    proc = live.core(*args, tty=gate == "no-packages")
    assert proc.returncode == 0, proc.stderr
    assert sorted(ran(proc)) == modules()
    assert not SUDO_WORK & set(live.commands), SUDO_WORK & set(live.commands)
    assert not (live.etc / POLICY).exists()
