"""Tests for infra/firefox/policies.json — the system Firefox policy install.sh ships.

The policy is the overlay's one write outside $HOME (see stage_firefox): Firefox
reads enterprise policies only from root-owned paths. This pins what it must
keep saying: telemetry and studies off, tracking protection on, uBlock Origin
force-installed.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_omarchy_install import OMARCHY_FIREFOX_POLICY

REPO_ROOT = Path(__file__).parent.parent.parent
POLICIES_JSON = REPO_ROOT / "infra" / "firefox" / "policies.json"
POLICIES = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))["policies"]
# What omarchy-install-browser copies to /usr/lib/firefox/distribution/ —
# read when Omarchy is installed (never written); the install suite's fixture
# of it stands in elsewhere (CI), so the merge check never skips.
OMARCHY_POLICY = Path("/usr/share/omarchy/default/firefox/policies.json")


def test_policy_keeps_the_privacy_defaults() -> None:
    assert POLICIES["DisableTelemetry"] is True
    assert POLICIES["DisableFirefoxStudies"] is True
    etp = POLICIES["EnableTrackingProtection"]
    assert etp["Value"] is True and etp["Cryptomining"] is True and etp["Fingerprinting"] is True
    ublock = POLICIES["ExtensionSettings"]["uBlock0@raymondhill.net"]
    assert ublock["installation_mode"] == "force_installed"
    assert "ublock-origin" in ublock["install_url"]


def _merge(base: dict, over: dict) -> dict:
    """jq's `*` (what stage_firefox runs): a recursive object merge, the
    right-hand side winning on a shared key."""
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def test_merged_with_omarchys_policy_it_keeps_every_omarchy_pref() -> None:
    """The installed file is Omarchy's own default/firefox/policies.json
    merged under ours (stage_firefox), because /etc/firefox/policies takes
    precedence over the distribution/ copy omarchy-install-browser writes
    and would otherwise shadow it. Checked against the installed Omarchy
    when there is one (read-only) — and then the install suite's fixture of
    that file may name no pref Omarchy no longer ships — else against the
    fixture, so CI exercises the merge too. On a shared pref ours wins."""
    ours_prefs = POLICIES.get("Preferences", {})
    if OMARCHY_POLICY.is_file():
        theirs = json.loads(OMARCHY_POLICY.read_text(encoding="utf-8"))
        fixture_only = set(OMARCHY_FIREFOX_POLICY["policies"]["Preferences"]) - set(ours_prefs)
        assert fixture_only <= set(theirs["policies"]["Preferences"]), fixture_only
    else:
        theirs = OMARCHY_FIREFOX_POLICY
    ours = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))
    merged = _merge(theirs, ours)["policies"]
    for pref, value in theirs["policies"].get("Preferences", {}).items():
        assert pref in merged["Preferences"], pref
        assert merged["Preferences"][pref] == ours_prefs.get(pref, value), pref
    for key in POLICIES:
        assert key in merged, key
    assert merged["DisableTelemetry"] is True
