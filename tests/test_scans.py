"""Static scans over every bash script the tree ships, one rule each (AGENTS.md rules 3,
6 and 8, and › Scripts), selected by shebang, the rule `make shellcheck` uses, and walked
on disk. Scanned rather than run, so every branch is covered."""

from __future__ import annotations

import re
import shutil
import stat
from pathlib import Path

import pytest

from conftest import NEEDS_OMARCHY, OMARCHY, REPO_ROOT, code, omarchy_names, shipped_bash

HEREDOC = re.compile(r"(?ms)<<-?\s*(['\"]?)(\w+)\1\n.*?^\s*\2$")
STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
USAGE_HEREDOC = re.compile(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$")
FROZEN_SEAM = re.compile(r"^\s*readonly\s+(_HYPRCONF_\w+|HYPRCONF_(?:STATS|GPU)_\w+)", re.M)


def rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def bare(text: str) -> str:
    """Comments, heredocs and quoted strings off: what runs. A message naming sudo is prose;
    a `$(…)` inside one is code, so every substitution's body is scanned as lines of its own."""
    text = HEREDOC.sub("", code(text))
    parts = [text]
    for m in re.finditer(r"\$\((?!\()", text):  # not $(( arithmetic ))
        depth, i = 1, m.end()
        while depth and i < len(text):
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        parts.append(text[m.end() : i - 1])
    return "\n".join(STRING.sub('""', part) for part in parts)


# AGENTS.md › Scripts: `set -euo pipefail`, with the deviations named there.
SET_LINE = {
    "hyprconf-yubikey": "set -uo pipefail",
    "10-hyprconf": "set -uo pipefail",
    "hyprconf-stats": "set -u",
}


def test_every_script_carries_the_documented_header() -> None:
    """`make shellcheck` selects BY the shebang, so a missing one is no lint rather than a
    failure; a `readonly` seam is one the suite cannot point at a fake."""
    for script in shipped_bash():
        text = script.read_text()
        assert text.startswith("#!/usr/bin/env bash\n"), rel(script)
        want = SET_LINE.get(script.name, "set -euo pipefail")
        assert re.search(rf"^{re.escape(want)}$", text, re.M), f"{rel(script)}: no `{want}` line"
        assert script.stat().st_mode & stat.S_IXUSR, f"{rel(script)}: not executable"
        assert not FROZEN_SEAM.search(text), f"{rel(script)}: readonly seam"


# Rule 3: no pacman, AUR helper, Omarchy AUR wrapper (/usr/bin/omarchy-pkg-aur-*,
# omarchy-update-aur-pkgs) or removal on any path; rule 6: no chsh. Over what runs.
FORBIDDEN = re.compile(
    r"\b(?:pacman|yay|paru|makepkg|chsh|omarchy-pkg-drop)\b|omarchy-pkg-aur-|omarchy-update-aur-pkgs"
)


def test_no_pacman_aur_wrapper_removal_or_chsh_on_any_path() -> None:
    for script in shipped_bash():
        hit = FORBIDDEN.search(bare(script.read_text(errors="ignore")))
        assert not hit, f"{rel(script)}: {hit.group(0)}"


def test_nothing_shipped_switches_the_active_theme() -> None:
    """Rule 6, over code() rather than bare(): a theme name in a string handed to the
    setter is the switch itself, and the two theme modules cite it only in comments."""
    for script in shipped_bash():
        text = code(script.read_text(errors="ignore"))
        assert "omarchy-theme-set" not in text, f"{rel(script)}: switches the active theme"


@pytest.mark.skipif(not (OMARCHY / "bin").is_dir(), reason=NEEDS_OMARCHY)
def test_every_omarchy_command_the_tree_runs_is_one_omarchy_ships() -> None:
    """The box's fakes are derived from these same names, so a command Omarchy renamed
    keeps a passing stub for ever: only a box that has Omarchy can catch it. Comments
    are dropped — they cite `omarchy-base` and `omarchy-settings`, which are not commands."""
    gone = [n for n in omarchy_names(code) if shutil.which(n, path=str(OMARCHY / "bin")) is None]
    assert not gone, f"no longer in {OMARCHY / 'bin'}: {gone}"


def test_every_packages_file_holds_plain_package_names() -> None:
    """A line starting with '-' would reach that module's sudo `omarchy-pkg-add` as an option."""
    files = sorted((REPO_ROOT / "modules").glob("*/packages"))
    assert files, "no module packages file found: the scan is broken"
    for path in files:
        for ln in path.read_text().splitlines():
            ln = ln.split("#", 1)[0].strip()
            assert not ln or re.fullmatch(r"[a-z0-9][a-z0-9@._+-]*", ln), (
                f"{path.parent.name}: {ln!r}"
            )


# Rule 8: clone-only over https. Whole-word curl / wget, any *sh pipe, process substitution,
# base64 -d and eval, over the code with its strings still in (a string handed to a shell is
# code) minus install.sh's usage heredoc, on the bash plus the zsh payload every interactive
# shell executes. Every exception is written here in full, or does not land.
FETCH_EXEC = (
    r"\bcurl\b",
    r"\bwget\b",
    r"\|&?\s*\w*sh\b",
    r"bash\s*<\(",
    r"source\s*<\(",
    r"base64\s+(?:-d|--decode)",
    r"(?<!hyprctl )\beval\b",
)
FETCH_EXEC_ALLOWED = (
    # zoxide's documented init: the output of a pacman-installed binary
    'command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init zsh)"',
)


def test_nothing_shipped_fetches_and_executes() -> None:
    zsh = REPO_ROOT / "modules" / "shell-zsh"
    for script in shipped_bash() + [zsh / "zshrc", zsh / ".p10k.zsh"]:
        text = USAGE_HEREDOC.sub("", code(script.read_text(errors="ignore")))
        for allowed in FETCH_EXEC_ALLOWED:
            text = text.replace(allowed, "")
        for pattern in FETCH_EXEC:
            assert not re.search(pattern, text), f"{rel(script)}: fetch-and-execute {pattern!r}"


# Rule 8: the whole of the tree's root surface, listed because the list IS the invariant —
# a `sudo` anywhere else moves it deliberately, through this file, or does not land. Each
# one's gate and undo: that module's README. The Makefile's SC2086 pass runs on the same three.
SUDO_CALLERS = {
    "modules/firefox/install",
    "modules/keychron/install",
    "modules/yubikey/bin/hyprconf-yubikey",
}


def test_every_root_write_carries_the_end_of_options_marker() -> None:
    """Nothing an unprivileged process can name may read as an option to a root command:
    every `sudo` carries ` -- ` (bin/omarchy-hibernation-setup:43,46's shape); `sudo
    udevadm …` takes no path and is the one exemption."""
    callers = set()
    for script in shipped_bash():
        for ln in bare(script.read_text(errors="ignore")).splitlines():
            if re.search(r"\bsudo\s", ln):
                callers.add(rel(script))
                ok = " -- " in ln or re.search(r"\bsudo\s+udevadm\s", ln)
                assert ok, f"{rel(script)}: {ln.strip()}"
    assert callers == SUDO_CALLERS
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert all(f in makefile for f in SUDO_CALLERS), "the SC2086 pass and SUDO_CALLERS differ"


def test_the_scans_see_inside_a_quoted_substitution() -> None:
    """The FORBIDDEN and sudo scans read bare(): a substitution inside a message is code."""
    assert FORBIDDEN.search(bare('ver="$(pacman -Q firefox)"'))
    assert "sudo tee" in bare('x="$(echo a | sudo tee "$f")"')
    assert not FORBIDDEN.search(bare('echo "install it with pacman -S foo"'))


def test_nothing_shipped_uses_the_dead_hyprctl_forms() -> None:
    """`hyprctl keyword` is a no-op and a two-token `dispatch dpms on` an error under the
    Lua parser (AGENTS.md › Scripts)."""
    dead = re.compile(
        r"hyprctl\s+(--batch\s+)?[\"']?keyword\b|hyprctl\s+dispatch\s+[a-z_]+\s+[a-z_]+"
    )
    offenders = [
        f"{rel(script)}:{n}: {ln.strip()}"
        for script in shipped_bash()
        for n, ln in enumerate(code(script.read_text(errors="ignore")).splitlines(), 1)
        if dead.search(ln)
    ]
    assert not offenders, "use hyprctl eval / hyprctl dispatch 'hl.dsp.…':\n" + "\n".join(offenders)
