"""PII guard (AGENTS.md rule 4): no file in the tree carries the author's identity, a
/home/<user>/ path, an email, a hostname or secret-shaped material. The identities are
derived at runtime and the whole tree is walked on disk."""

from __future__ import annotations

import getpass
import os
import re
import socket
import subprocess
from pathlib import Path

from conftest import REPO_ROOT

# /home/<name>/ at a path boundary; the generic placeholders are allowed.
HOME_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._/-])/home/(?!\$|user\b|username\b|<|USER\b)[A-Za-z0-9._-]+/"
)
# Shared, machine-provided or placeholder accounts, and the two project names: "omarchy" is
# the hostname Omarchy's installer defaults to (install/provisioning/setup-form.sh:84).
GENERIC_ACCOUNTS = frozenset(
    "root home user users username test tester testuser someone nobody admin arch archlinux "
    "build builder ubuntu docker vagrant omarchy hyprconf".split()
)
SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".vscode"})
# Tool-managed local state, never committed (.gitignore); the tracked settings.json stays scanned.
SKIP_FILES = frozenset({".claude/settings.local.json", ".claude/RESUME.md"})
# Credential formats rule 4 names that no identity string would catch; a match is reported
# by file and line, never echoed.
SECRET_RES = tuple(
    re.compile(p)
    for p in (
        r"AKIA[0-9A-Z]{16}",
        r"ASIA[0-9A-Z]{16}",
        r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----",
        r"ghp_[A-Za-z0-9]{36}",
        r"github_pat_[A-Za-z0-9_]{22,}",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
        r"aws_secret_access_key\s*=",
    )
)


def repo_files() -> list[Path]:
    """Every regular file in the checkout: a walk, not `git ls-files`, so a stray scratch
    file is caught before it is ever added."""
    out = []
    for path in sorted(REPO_ROOT.rglob("*")):
        rel = path.relative_to(REPO_ROOT)
        if set(rel.parts) & SKIP_DIRS or str(rel) in SKIP_FILES:
            continue
        if path.is_file() and not path.is_symlink():
            out.append(path)
    return out


def text_lines(path: Path) -> list[str]:
    """No suffix list: a tool-exported .svg is exactly where an editor embeds a /home path."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []


def identities() -> set[str]:
    """Whoever runs the suite: login, home directory name, hostname and git email, nothing
    hard-coded, so this file is never the leak; generic or under three characters is dropped."""
    names = {
        os.environ.get("USER", ""),
        os.environ.get("SUDO_USER", ""),
        os.environ.get("LOGNAME", ""),
        Path.home().name,
        socket.gethostname().split(".")[0],
    }
    try:
        names.add(getpass.getuser())
    except (KeyError, OSError):
        pass
    out = {n for n in names if len(n) >= 3 and n.lower() not in GENERIC_ACCOUNTS}
    email = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "config", "--get", "user.email"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if "@" in email:
        out.add(email)
    return out


def offenders(patterns: list[re.Pattern[str]], *, echo: bool = False) -> list[str]:
    """`<file>:<line>` for every matching line in the tree, this file included; `echo`
    appends the line, safe for a path, never for an identity or a secret a CI log republishes."""
    return [
        f"{path.relative_to(REPO_ROOT)}:{n}" + (f": {ln.strip()}" if echo else "")
        for path in repo_files()
        for n, ln in enumerate(text_lines(path), 1)
        if any(p.search(ln) for p in patterns)
    ]


def test_no_hardcoded_home_paths_anywhere() -> None:
    found = offenders([HOME_PATH_RE], echo=True)
    assert not found, "Hardcoded /home/<user>/ paths (use ~ or $HOME):\n" + "\n".join(found)


def test_no_personal_identities_anywhere() -> None:
    """A shared or CI account whose every name is generic leaves nothing to search for,
    and the assertion passes on an empty pattern list rather than skipping."""
    found = offenders(
        [re.compile(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9])", re.I) for i in identities()]
    )
    assert not found, "Personal identity in the tree (use 'testuser', ~ or $HOME):\n" + "\n".join(
        found
    )


def test_no_secret_material_anywhere() -> None:
    found = offenders(list(SECRET_RES))
    assert not found, "Secret-shaped material in tracked files: " + ", ".join(found)
