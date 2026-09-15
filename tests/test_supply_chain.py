"""Supply-chain pins (AGENTS.md rule 8): the artifacts strangers trust before and while
running the overlay, frozen as text so a regression cannot ship green. The model, and what
to do when one has to move: CONTRIBUTING › Security."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ONE_LINER = "bash <(curl -fsSL --proto '=https' https://hyprconf.sh)"
# The landing page shows the short form instead, by the author's decision: it reads as one
# line on the page and rides hyprconf.sh's 301 from http. That first hop IS plaintext, so
# the page's command is frozen here rather than left unpinned — a widening (a second host,
# a pipe straight into bash) still has to come through this file. Every copy-paste command
# in the docs keeps its explicit https. Why: CONTRIBUTING › Security.
WEB_ONE_LINER = "bash &lt;(curl -fsSL hyprconf.sh)"
# The only remote URLs the page may carry: the repository, its own origin, the SVG namespace.
WEB_ALLOWED_URLS = (
    "https://github.com/ak4dev/.hyprconf",
    "https://hyprconf.sh",
    "http://www.w3.org/2000/svg",
)


def test_web_page_is_self_contained() -> None:
    """The page's whole job is to be trusted enough to pipe into bash: no script element,
    no external resource, no protocol-relative fetch, no inline handler."""
    for path in sorted((REPO_ROOT / "web").iterdir()):
        text = path.read_text(encoding="utf-8")
        assert "<script" not in text.lower(), f"{path.name}: script element"
        for url in re.findall(r"https?://[^\s\"'<>()]+", text):
            assert any(url.startswith(a) for a in WEB_ALLOWED_URLS), f"{path.name}: {url}"
        assert not re.search(r"(?:href|src)\s*=\s*[\"']//", text), f"{path.name}: //-URL"
        assert "url(//" not in text, f"{path.name}: protocol-relative CSS url"
        assert not re.search(r"\son\w+\s*=", text), f"{path.name}: inline event handler"


def test_published_one_liners_are_https_only() -> None:
    """Schemeless, curl's first request is plaintext port 80, answered by an on-path attacker —
    so every command a reader copies out of the docs names https. The landing page is the one
    deliberate exception and is pinned as text instead, WEB_ONE_LINER above."""
    for rel in ("README.md", "install.sh", "docs/CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for m in re.finditer(r"curl [^\n]*hyprconf\.sh", text):
            assert "https://hyprconf.sh" in m.group(0), f"{rel}: schemeless: {m.group(0)!r}"
    web = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert WEB_ONE_LINER in web, "the landing page's one-liner moved"
    assert web.count("curl") == 1, "a second curl command appeared on the page"
    assert ONE_LINER in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_bootstrap_defaults_are_pinned_https_and_stable() -> None:
    """The first bytes strangers run; every behavioural curl-path test overrides HYPRCONF_REPO."""
    text = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    assert ': "${HYPRCONF_REPO:=https://github.com/ak4dev/.hyprconf}"' in text
    assert ': "${HYPRCONF_BRANCH:=stable}"' in text


def test_ci_workflow_is_least_privilege() -> None:
    workflows = sorted((REPO_ROOT / ".github/workflows").glob("*.y*ml"))
    assert workflows, "no CI workflow found"
    for wf in workflows:
        text = wf.read_text(encoding="utf-8")
        assert re.search(r"^permissions:\n  contents: read$", text, re.M), f"{wf.name}: token scope"
        assert text.count("permissions:") == 1, f"{wf.name}: a second permissions block"
        assert "pull_request_target" not in text and "secrets." not in text, wf.name
        for use in re.findall(r"uses:\s*(\S+)", text):
            assert re.search(r"@[0-9a-f]{40}$", use), f"{wf.name}: mutable action pin {use!r}"


def test_claude_settings_guardrails_keep_their_entries() -> None:
    """AGENTS.md's speed bump; the rules match command text, so each AUR entry point by name."""
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    assert {
        "Edit(//usr/share/omarchy/**)",
        "Bash(sudo pacman:*)",
        "Bash(yay:*)",
        "Bash(sudo yay:*)",
        "Bash(paru:*)",
        "Bash(makepkg:*)",
        "Bash(omarchy-pkg-aur-add:*)",
        "Bash(omarchy-pkg-aur-install:*)",
        "Bash(omarchy-update-aur-pkgs:*)",
    } <= set(settings["permissions"]["deny"])
    assert {
        "Bash(git push:*)",
        "Bash(git -C * push:*)",
        "Bash(*scripts/publish*)",
        "Bash(aws:*)",
        "Bash(*/aws *)",
    } <= set(settings["permissions"]["ask"])


def test_every_module_clone_is_pinned_to_a_reviewed_commit() -> None:
    """Third-party code a module clones runs on the user's box, so it stays at a commit
    somebody read: every `git clone` names a `--revision=$<name>pin`, no module pulls, and
    bumping a pin is a deliberate commit through the publish gates."""
    for install in sorted((REPO_ROOT / "modules").glob("*/install")):
        name, lines = install.parent.name, install.read_text(encoding="utf-8").splitlines()
        text = "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))
        for clone in re.findall(r"git clone[^\n]*", text):
            assert re.search(r'--revision="?\$[a-z0-9_]*pin', clone), f"{name}: {clone}"
        assert "git pull" not in text, name
    shell = (REPO_ROOT / "modules" / "shell-zsh" / "install").read_text(encoding="utf-8")
    assert re.search(r"^p10k_url=https://", shell, re.M)
    assert re.search(r"^p10k_pin=[0-9a-f]{40}$", shell, re.M)
