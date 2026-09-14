"""Static scans over every bash script the tree ships, one rule each
(AGENTS.md › Hard rules 3, 6 and 8, › Scripts): the documented header, no
package manager or `chsh` on any path, no fetch-and-execute, root writes with
the end-of-options marker, the working `hyprctl` forms, and plain names in
every `packages` file. Scanned rather than run, so every branch is covered.
The scripts are selected by their shebang — the rule `make shellcheck` uses —
and walked on disk, so the scan needs neither git nor a checkout git trusts.

HERMETIC: reads of the checkout only.
"""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "tests", "docs", "__pycache__", ".pytest_cache", ".ruff_cache"}


def shipped_bash() -> list[Path]:
    """Every bash script in the tree: install.sh, the hook, each module's
    `install`, `hook` and `bin/` tools, and scripts/publish."""
    out = []
    for p in sorted(REPO_ROOT.rglob("*")):
        if not p.is_file() or SKIP & set(p.relative_to(REPO_ROOT).parts):
            continue
        with p.open("rb") as fh:
            first = fh.readline()
        if first.startswith(b"#!") and b"bash" in first:
            out.append(p)
    assert out, "no bash scripts found — the scan is broken"
    return out


def rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def code(text: str) -> str:
    """Comments off: a rule about what a script does is never satisfied — or
    tripped — by a comment about it."""
    return "\n".join(
        ln.split(" #", 1)[0] for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )


HEREDOC = re.compile(r"(?ms)<<-?\s*(['\"]?)(\w+)\1\n.*?^\s*\2$")
STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')


def bare(text: str) -> str:
    """Comments, heredocs and quoted strings off — what is left is what runs.
    A usage text that names pacman, or a message that names sudo, is prose."""
    return STRING.sub('""', HEREDOC.sub("", code(text)))


# ---------------------------------------------------------------------------
# The header every script carries
# ---------------------------------------------------------------------------

# AGENTS.md › Scripts: `#!/usr/bin/env bash` and `set -euo pipefail`, with the
# deviations named there — the two hooks and hyprconf-yubikey drop -e (they
# handle their own failures), hyprconf-stats is `set -u`. The map IS that
# list, so a script that quietly drops a guard fails here.
SET_LINE = {
    "hyprconf-yubikey": "set -uo pipefail",
    "10-hyprconf": "set -uo pipefail",  # hooks/10-hyprconf, the post-update hook
    "hook": "set -uo pipefail",  # modules/firefox-theme's theme-set hook
    "hyprconf-stats": "set -u",
}


@pytest.mark.parametrize("script", shipped_bash(), ids=rel)
def test_every_script_carries_the_documented_header(script: Path) -> None:
    """`make shellcheck` selects scripts BY the shebang, so a missing one
    means no lint at all rather than a failure: this is what catches that.
    Every script carries the exec bit — the hooks too, though
    `omarchy-hook-install` chmods its copy anyway (bin/omarchy-hook-install:29).
    A seam stays overridable, or the suite cannot point it at a fake."""
    text = script.read_text()
    assert text.startswith("#!/usr/bin/env bash\n"), script
    want = SET_LINE.get(script.name, "set -euo pipefail")
    assert re.search(rf"^{re.escape(want)}$", text, re.M), f"{rel(script)}: no `{want}` line"
    assert script.stat().st_mode & stat.S_IXUSR, f"{rel(script)}: not executable"
    frozen = re.findall(r"^\s*readonly\s+(_HYPRCONF_\w+|HYPRCONF_(?:STATS|GPU)_\w+)", text, re.M)
    assert not frozen, f"{rel(script)}: readonly seam {frozen}"


# ---------------------------------------------------------------------------
# Packages: Omarchy's front-end and nothing else; the login shell stays bash
# ---------------------------------------------------------------------------

# Rule 3 forbids pacman on ANY path, the AUR wrappers Omarchy ships (-add,
# -install, -accessible: /usr/bin/omarchy-pkg-aur-*, and the AUR half of its
# updater) and every removal; rule 6 forbids `chsh`. Whole words, over what
# runs — a message that says "see pacman's error above" is prose.
FORBIDDEN = (
    r"\bpacman\b",
    r"\byay\b",
    r"\bparu\b",
    r"\bmakepkg\b",
    r"\bchsh\b",
    r"\bomarchy-pkg-drop\b",
    r"omarchy-pkg-aur-",
    r"omarchy-update-aur-pkgs",
)


def test_no_pacman_aur_wrapper_removal_or_chsh_on_any_path() -> None:
    for script in shipped_bash():
        text = bare(script.read_text(errors="ignore"))
        for pattern in FORBIDDEN:
            assert not re.search(pattern, text), f"{rel(script)}: {pattern}"


def test_every_packages_file_holds_plain_package_names() -> None:
    """A line starting with '-' would reach that module's sudo `omarchy-pkg-add`
    as an option, not a package. One rule over every module's own file; each
    line may carry a trailing `# why`, which comes off the way each `install`
    takes it off."""
    files = sorted((REPO_ROOT / "modules").glob("*/packages"))
    assert files, "no module packages file found — the scan is broken"
    for path in files:
        for ln in path.read_text().splitlines():
            ln = ln.split("#", 1)[0].strip()
            if ln:
                assert re.fullmatch(r"[a-z0-9][a-z0-9@._+-]*", ln), f"{path.parent.name}: {ln!r}"


# ---------------------------------------------------------------------------
# Security (rule 8): clone-only over https, and root writes with `--`
# ---------------------------------------------------------------------------

# The overlay's network trust is clone-only over https: fetching content and
# executing it would add a trust root the model never had (CONTRIBUTING ›
# Security). Every exception is written down here, in full, or does not land.
# Whole-word curl/wget on purpose: URL-first invocations and `sh -c "$(curl
# …)"` all carry the word; the pipe net catches any *sh interpreter. Over the
# code with its strings still in — a string handed to a shell is code too —
# minus install.sh's usage heredoc, which documents the curl one-liner.
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
    # zoxide's documented init: output of a pacman-installed binary
    'command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init zsh)"',
)
USAGE_HEREDOC = re.compile(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$")


def fetch_exec_surface() -> list[Path]:
    """The shipped bash plus the shell payload the shebang rule misses — the
    rc file and p10k config every interactive zsh executes (modules/shell-zsh)."""
    zsh = REPO_ROOT / "modules" / "shell-zsh"
    return shipped_bash() + [zsh / "zshrc", zsh / ".p10k.zsh"]


def test_nothing_shipped_fetches_and_executes() -> None:
    for script in fetch_exec_surface():
        text = USAGE_HEREDOC.sub("", code(script.read_text(errors="ignore")))
        for allowed in FETCH_EXEC_ALLOWED:
            text = text.replace(allowed, "")
        for pattern in FETCH_EXEC:
            assert not re.search(pattern, text), (
                f"{rel(script)}: fetch-and-execute shape {pattern!r}"
            )


def test_every_root_write_carries_the_end_of_options_marker() -> None:
    """Nothing an unprivileged process can name may be read as an option by a
    root command: every `sudo` call carries ` -- ` before its operands
    (Omarchy's own `mv -Tf --` / `rm -f --` shape, bin/omarchy-hibernation-
    setup:43,46). `sudo udevadm …` takes no path and is the one exemption;
    modules/yubikey's `run_root` helpers are `sudo --` and `sudo -n --`."""
    seen = 0
    for script in shipped_bash():
        for ln in bare(script.read_text(errors="ignore")).splitlines():
            if not re.search(r"\bsudo\s", ln):
                continue
            seen += 1
            assert " -- " in ln or re.search(r"\bsudo\s+udevadm\s", ln), (
                f"{rel(script)}: {ln.strip()}"
            )
    assert seen, "no sudo call found — the scan is broken"


# ---------------------------------------------------------------------------
# Hyprland: the forms that work under the Lua parser
# ---------------------------------------------------------------------------


def test_nothing_shipped_uses_the_dead_hyprctl_forms() -> None:
    """`hyprctl keyword` is a no-op and a two-token `hyprctl dispatch dpms on`
    an error under Hyprland 0.56's Lua parser; the working forms are `hyprctl
    eval` and `hyprctl dispatch 'hl.dsp.…'` (AGENTS.md › Known quirks)."""
    dead = re.compile(
        r"hyprctl\s+(--batch\s+)?[\"']?keyword\b|hyprctl\s+dispatch\s+[a-z_]+\s+[a-z_]+"
    )
    offenders = [
        f"{rel(script)}:{lineno}: {line.strip()}"
        for script in shipped_bash()
        for lineno, line in enumerate(code(script.read_text(errors="ignore")).splitlines(), 1)
        if dead.search(line)
    ]
    assert not offenders, "use hyprctl eval / hyprctl dispatch 'hl.dsp.…':\n" + "\n".join(offenders)
