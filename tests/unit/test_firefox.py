"""Tests for infra/firefox/policies.json — the system Firefox policy install.sh ships.

The policy is the overlay's one write outside $HOME (see stage_firefox): Firefox
reads enterprise policies only from root-owned paths. These tests pin what it
must keep saying: telemetry and studies off, Pocket off, tracking protection on,
uBlock Origin force-installed.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
POLICIES_JSON = REPO_ROOT / "infra" / "firefox" / "policies.json"


# ---------------------------------------------------------------------------
# infra/firefox/policies.json
# ---------------------------------------------------------------------------


def test_policies_json_exists() -> None:
    assert POLICIES_JSON.exists(), "infra/firefox/policies.json must exist"


def test_policies_json_valid() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    assert "policies" in data


def test_policies_json_disables_telemetry() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    policies = data["policies"]
    assert policies.get("DisableTelemetry") is True


def test_policies_json_disables_studies() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    assert data["policies"].get("DisableFirefoxStudies") is True


def test_policies_json_disables_pocket() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    assert data["policies"].get("DisablePocket") is True


def test_policies_json_ublock_origin_installed() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    ext_settings = data["policies"].get("ExtensionSettings", {})
    ublock = ext_settings.get("uBlock0@raymondhill.net")
    assert ublock is not None, "uBlock Origin must be in ExtensionSettings"
    assert "install_url" in ublock
    assert "installation_mode" in ublock
    assert "ublock-origin" in ublock["install_url"]


def test_policies_json_tracking_protection_enabled() -> None:
    data = json.loads(POLICIES_JSON.read_text())
    etp = data["policies"].get("EnableTrackingProtection", {})
    assert etp.get("Value") is True
    assert etp.get("Cryptomining") is True
    assert etp.get("Fingerprinting") is True
