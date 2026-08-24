"""Tests for infra/firefox/policies.json — the system Firefox policy install.sh ships.

The policy is the overlay's one write outside $HOME (see stage_firefox): Firefox
reads enterprise policies only from root-owned paths. This pins what it must
keep saying: telemetry and studies off, tracking protection on, uBlock Origin
force-installed.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POLICIES_JSON = REPO_ROOT / "infra" / "firefox" / "policies.json"
POLICIES = json.loads(POLICIES_JSON.read_text(encoding="utf-8"))["policies"]


def test_policy_keeps_the_privacy_defaults() -> None:
    assert POLICIES["DisableTelemetry"] is True
    assert POLICIES["DisableFirefoxStudies"] is True
    etp = POLICIES["EnableTrackingProtection"]
    assert etp["Value"] is True and etp["Cryptomining"] is True and etp["Fingerprinting"] is True
    ublock = POLICIES["ExtensionSettings"]["uBlock0@raymondhill.net"]
    assert ublock["installation_mode"] == "force_installed"
    assert "ublock-origin" in ublock["install_url"]
