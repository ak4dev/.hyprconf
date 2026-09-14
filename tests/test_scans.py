"""Static scans over every bash script the tree ships, one rule each (AGENTS.md rules 3,
6 and 8, and › Scripts), selected by shebang, the rule `make shellcheck` uses, and walked
on disk. Scanned rather than run, so every branch is covered."""

from __future__ import annotations

import re
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "tests", "docs", "__pycache__", ".pytest_cache", ".ruff_cache"}
HEREDOC = re.compile(r"(?ms)<<-?\s*(['\"]?)(\w+)\1\n.*?^\s*\2$")
STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
USAGE_HEREDOC = re.compile(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$")
FROZEN_SEAM = re.compile(r"^\s*readonly\s+(_HYPRCONF_\w+|HYPRCONF_(?:STATS|GPU)_\w+)", re.M)


def shipped_bash() -> list[Path]:
    out = []
    for p in sorted(REPO_ROOT.rglob("*")):
        if p.is_file() and not SKIP & set(p.relative_to(REPO_ROOT).parts):
            with p.open("rb") as fh:
                first = fh.readline()
            if first.startswith(b"#!") and b"bash" in first:
                out.append(p)
    assert out, "no bash scripts found: the scan is broken"
    return out


def rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def code(text: str) -> str:
    """Comments off: a rule about what a script does is never met, or tripped, by a comment."""
    lines = (ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    return "\n".join(ln.split(" #", 1)[0] for ln in lines)


def bare(text: str) -> str:
    """Comments, heredocs and quoted strings off: what runs. A message naming sudo is prose."""
    return STRING.sub('""', HEREDOC.sub("", code(text)))


# AGENTS.md › Scripts: `set -euo pipefail`, with the deviations named there.
SET_LINE = {
    "hyprconf-yubikey": "set -uo pipefail",
    "10-hyprconf": "set -uo pipefail",
    "hook": "set -uo pipefail",
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


def test_every_root_write_carries_the_end_of_options_marker() -> None:
    """Nothing an unprivileged process can name may read as an option to a root command:
    every `sudo` carries ` -- ` (bin/omarchy-hibernation-setup:43,46's shape); `sudo
    udevadm …` takes no path and is the one exemption."""
    seen = 0
    for script in shipped_bash():
        for ln in bare(script.read_text(errors="ignore")).splitlines():
            if re.search(r"\bsudo\s", ln):
                seen += 1
                ok = " -- " in ln or re.search(r"\bsudo\s+udevadm\s", ln)
                assert ok, f"{rel(script)}: {ln.strip()}"
    assert seen, "no sudo call found: the scan is broken"


def test_nothing_shipped_uses_the_dead_hyprctl_forms() -> None:
    """`hyprctl keyword` is a no-op and a two-token `dispatch dpms on` an error under the
    Lua parser (AGENTS.md › Known quirks)."""
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
