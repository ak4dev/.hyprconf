"""
PII guard tests.

No file in the tree may carry personal information about the person who authored it
— a real username, an absolute /home/<user>/ path, or a personal email address.
Two separate reasons: the overlay's configs (hypr/, kitty/, zsh/, plugins/ …)
are installed into any user's $HOME, so a hardcoded path is broken on every
other machine; and the repo is published, so a name in it is published too.

Scope is deliberately the WHOLE repository — a bare username in a test
fixture is as published as one in a config, and a guard that covers part of
the tree teaches you to trust it everywhere.

The identities searched for are derived at runtime (_identities below).
"""

from __future__ import annotations

import getpass
import os
import re
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# /home/<name>/ — a real per-user absolute path. Generic placeholders
# (/home/$USER, /home/user, /home/username, /home/<user>) are allowed.
#
# The leading lookbehind requires the match to begin at a path boundary, so a
# substring like ".../not/home/directory/" in prose is not mistaken for an
# absolute home path. Both exclusions exist to keep the check precise: a rule
# that cries wolf on vendored upstream comments gets muted, and then it stops
# catching the real thing.
HOME_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._/-])/home/(?!\$|user\b|username\b|<|USER\b)[A-Za-z0-9._-]+/"
)

# Shared, machine-provided or placeholder accounts. A match on one of these is
# not a leak, and CI runs the suite as root — without this the check would
# either flag every "root" in the tree or, worse, be quietly meaningless there.
# "home": GitHub's container jobs set HOME=/github/home, whose basename is a
# directory name, not a person — and it would match every $HOME in the tree.
GENERIC_ACCOUNTS = frozenset(
    {
        "root",
        "home",
        "user",
        "users",
        "username",
        "test",
        "tester",
        "testuser",
        "someone",
        "nobody",
        "admin",
        "arch",
        "archlinux",
        "build",
        "builder",
        "runner",
        "ubuntu",
        "github",
        "docker",
        "vagrant",
        # Project and vendor names, never people. "omarchy" is the hostname
        # Omarchy's own installer defaults to (OMARCHY_HOSTNAME_DEFAULT='omarchy',
        # /usr/share/omarchy/install/provisioning/setup-form.sh:84, and the
        # prompt "or return for 'omarchy'" at :155) — on a box that took it,
        # the hostname identity flagged every "omarchy" in the tree, 1700
        # lines across 57 files, and "hyprconf" would do the same for 785.
        "omarchy",
        "hyprconf",
    }
)

# Directories that are never part of what gets published: git's own store and
# tool caches.
SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".vscode"})

# Tool-managed local state, never committed (why: .gitignore). The tracked
# .claude/settings.json stays scanned.
SKIP_FILES = frozenset({".claude/settings.local.json", ".claude/RESUME.md"})

# Credential formats rule 4 names but no identity string would catch: fixed,
# low-false-positive shapes only. Matches are reported by file and line
# number, never echoed.
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


def _repo_files() -> list[Path]:
    """Every regular file in the checkout, skipping SKIP_DIRS. A directory
    walk rather than `git ls-files`, so the scan needs neither git nor a
    checkout git is willing to trust — and a stray scratch file is caught
    before it is ever added."""
    out: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if str(rel) in SKIP_FILES:
            continue
        if path.is_file() and not path.is_symlink():
            out.append(path)
    return out


def _text_lines(path: Path) -> list[str]:
    """Every line of `path`, or nothing if it is not UTF-8 text. No suffix
    list: the only files that fail this are the repo's two images, and
    skipping by suffix is how a tool-exported .svg — exactly where an editor
    embeds an absolute /home/<user> path (Inkscape's sodipodi:docname) —
    stops being scanned."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []  # binary / unreadable — not a file we author


def _identities() -> set[str]:
    """Names and addresses that must not appear anywhere in the tree.

    Derived from whoever is running the suite — their login name, their home
    directory's name, this machine's hostname and their configured git email.
    Nothing is hard-coded, so this file never becomes the leak. Anything
    generic or too short to match precisely is dropped: a two-character login
    would match half the prose in the repo.
    """
    names = {
        os.environ.get("USER", ""),
        os.environ.get("SUDO_USER", ""),
        os.environ.get("LOGNAME", ""),
        Path.home().name,
        socket.gethostname().split(".")[0],
    }
    try:
        names.add(getpass.getuser())
    except (KeyError, OSError):  # no passwd entry for this uid
        pass

    identities = {n for n in names if len(n) >= 3 and n.lower() not in GENERIC_ACCOUNTS}

    email = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "config", "--get", "user.email"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if "@" in email:
        identities.add(email)

    return identities


def _offenders(patterns: list[re.Pattern[str]], *, echo: bool = False) -> list[str]:
    """`<file>:<line>` for every line matching any pattern, over every file in
    the tree — this one included, which is the check that its own promise to
    write no identity down holds. `echo` appends the offending line: safe for
    a /home path, never for an identity or a secret, which a CI log or a
    pasted terminal would then republish."""
    out: list[str] = []
    for path in _repo_files():
        for lineno, line in enumerate(_text_lines(path), 1):
            if any(p.search(line) for p in patterns):
                rel = path.relative_to(REPO_ROOT)
                out.append(f"{rel}:{lineno}: {line.strip()}" if echo else f"{rel}:{lineno}")
    return out


def test_no_hardcoded_home_paths_anywhere() -> None:
    offenders = _offenders([HOME_PATH_RE], echo=True)
    assert not offenders, "Hardcoded /home/<user>/ paths found (use ~ or $HOME):\n" + "\n".join(
        offenders
    )


def test_no_personal_identities_anywhere() -> None:
    """No file in the tree may name the person running the suite."""
    identities = _identities()
    if not identities:
        pytest.skip("no non-generic identity to search for (shared or CI account)")
    offenders = _offenders(
        [re.compile(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9])", re.I) for i in identities]
    )
    assert not offenders, (
        "Personal identity (username or git email) found in the tree.\n"
        "Replace it with a placeholder such as 'testuser', ~ or $HOME:\n" + "\n".join(offenders)
    )


def test_no_secret_material_anywhere() -> None:
    """Rule 4 bans keys and AWS ids; the identity scan cannot see them. A
    pasted credential would otherwise ride the publish pipeline onto the
    public stable branch."""
    offenders = _offenders(list(SECRET_RES))
    assert not offenders, "Secret-shaped material in tracked files: " + ", ".join(offenders)
