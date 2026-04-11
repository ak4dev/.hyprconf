"""
Tests for the deploy infrastructure (infra/deploy.sh, web/deploy.sh, teardown.sh).

Validates script syntax, required functions, the web deploy integration,
and the CloudFront function source file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
INFRA_DIR = REPO_ROOT / "infra"
WEB_DIR = REPO_ROOT / "web"
DEPLOY_SCRIPT = INFRA_DIR / "deploy.sh"
TEARDOWN_SCRIPT = INFRA_DIR / "teardown.sh"
WEB_DEPLOY_SCRIPT = WEB_DIR / "deploy.sh"
CF_FUNCTION = INFRA_DIR / "cloudfront-function.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Script syntax validation
# ---------------------------------------------------------------------------

class TestScriptSyntax:
    """All bash scripts must pass bash -n syntax check."""

    def test_deploy_sh_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(DEPLOY_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"deploy.sh syntax error:\n{result.stderr}"

    def test_teardown_sh_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(TEARDOWN_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"teardown.sh syntax error:\n{result.stderr}"

    def test_web_deploy_sh_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(WEB_DEPLOY_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"web/deploy.sh syntax error:\n{result.stderr}"


# ---------------------------------------------------------------------------
# deploy.sh function structure
# ---------------------------------------------------------------------------

class TestDeployFunctions:
    """deploy.sh must contain all required pipeline functions."""

    def test_deploy_bucket_exists(self) -> None:
        assert "deploy_bucket()" in _read(DEPLOY_SCRIPT)

    def test_deploy_web_exists(self) -> None:
        assert "deploy_web()" in _read(DEPLOY_SCRIPT)

    def test_deploy_cert_exists(self) -> None:
        assert "deploy_cert()" in _read(DEPLOY_SCRIPT)

    def test_deploy_cdn_exists(self) -> None:
        assert "deploy_cdn()" in _read(DEPLOY_SCRIPT)

    def test_deploy_dns_exists(self) -> None:
        assert "deploy_dns()" in _read(DEPLOY_SCRIPT)

    def test_deploy_cf_function_exists(self) -> None:
        assert "_deploy_cf_function()" in _read(DEPLOY_SCRIPT)

    def test_invalidate_cdn_exists(self) -> None:
        assert "_invalidate_cdn()" in _read(DEPLOY_SCRIPT)


# ---------------------------------------------------------------------------
# Web deploy integration
# ---------------------------------------------------------------------------

class TestWebDeployIntegration:
    """Web deploy must be integrated into the main pipeline."""

    def test_main_calls_deploy_web(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "deploy_web" in text

    def test_web_only_mode(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert 'web_only' in text or '"web"' in text

    def test_s3_sync_excludes_install_sh(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert '--exclude "install.sh"' in text or "--exclude 'install.sh'" in text

    def test_index_html_no_cache(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "no-cache" in text and "index.html" in text

    def test_web_deploy_is_thin_wrapper(self) -> None:
        text = _read(WEB_DEPLOY_SCRIPT)
        assert "infra/deploy.sh" in text
        assert "web" in text


# ---------------------------------------------------------------------------
# Bucket policy covers all objects
# ---------------------------------------------------------------------------

class TestBucketPolicy:
    """Bucket policy must allow public read on all objects, not just install.sh."""

    def test_policy_covers_all_objects(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "/*" in text
        # The old install.sh-only policy SID should be gone
        lines = text.splitlines()
        for line in lines:
            if "PublicReadInstallScript" in line:
                raise AssertionError("Old install.sh-only policy SID still present")

    def test_ensure_bucket_policy_function_exists(self) -> None:
        assert "_ensure_bucket_policy()" in _read(DEPLOY_SCRIPT)

    def test_ensure_bucket_policy_verifies(self) -> None:
        """Policy enforcement must verify the applied policy."""
        text = _read(DEPLOY_SCRIPT)
        assert "get-bucket-policy" in text

    def test_web_only_path_enforces_policy(self) -> None:
        """The web-only deploy path must also enforce bucket policy."""
        text = _read(DEPLOY_SCRIPT)
        # Find the web_only block and verify _ensure_bucket_policy is called
        in_web_only = False
        found = False
        for line in text.splitlines():
            if "web_only" in line and "then" in line:
                in_web_only = True
            if in_web_only and "_ensure_bucket_policy" in line:
                found = True
                break
            if in_web_only and "else" in line:
                break
        assert found, "web-only path must call _ensure_bucket_policy"


# ---------------------------------------------------------------------------
# CloudFront function
# ---------------------------------------------------------------------------

class TestCloudFrontFunction:
    """CloudFront function must route correctly."""

    def test_cf_function_exists(self) -> None:
        assert CF_FUNCTION.is_file()

    def test_cf_function_routes_curl(self) -> None:
        text = _read(CF_FUNCTION)
        assert "curl" in text
        assert "install.sh" in text

    def test_cf_function_routes_browser_to_spa(self) -> None:
        text = _read(CF_FUNCTION)
        assert "index.html" in text

    def test_cf_function_passes_static_assets(self) -> None:
        text = _read(CF_FUNCTION)
        # The regex !/\.\w+$/ ensures file-extension URIs pass through
        assert r"\.\w+$" in text or ".w+" in text

    def test_deploy_references_cf_function(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "hyprconf-ua-router" in text
        assert "cloudfront-function.js" in text

    def test_cf_function_association_is_automated(self) -> None:
        """CF function association must be done programmatically, not manually."""
        text = _read(DEPLOY_SCRIPT)
        assert "_ensure_cf_function_association" in text
        assert "update-distribution" in text

    def test_cf_function_uses_explicit_stage(self) -> None:
        """describe-function should use explicit --stage DEVELOPMENT."""
        text = _read(DEPLOY_SCRIPT)
        assert "--stage DEVELOPMENT" in text

    def test_default_root_object_is_index_html(self) -> None:
        """Existing distributions must have DefaultRootObject updated to index.html."""
        text = _read(DEPLOY_SCRIPT)
        assert "DefaultRootObject" in text
        assert "'index.html'" in text or '"index.html"' in text


# ---------------------------------------------------------------------------
# Teardown covers CF function
# ---------------------------------------------------------------------------

class TestTeardown:
    """Teardown must clean up all resources including CF function."""

    def test_teardown_removes_cf_function(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "hyprconf-ua-router" in text
        assert "delete-function" in text

    def test_teardown_removes_distribution(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "delete-distribution" in text

    def test_teardown_removes_bucket(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "delete-bucket" in text

    def test_teardown_removes_cert(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "delete-certificate" in text

    def test_teardown_removes_dns(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "change-resource-record-sets" in text
