"""
Tests for the deploy infrastructure (infra/deploy.sh, teardown.sh, CDK stack).

Validates script syntax, required functions, CDK integration, the web deploy
pipeline, and the CloudFront function source file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
INFRA_DIR = REPO_ROOT / "infra"
CDK_DIR = INFRA_DIR / "cdk"
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
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"deploy.sh syntax error:\n{result.stderr}"

    def test_teardown_sh_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(TEARDOWN_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"teardown.sh syntax error:\n{result.stderr}"

    def test_web_deploy_sh_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(WEB_DEPLOY_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"web/deploy.sh syntax error:\n{result.stderr}"


# ---------------------------------------------------------------------------
# deploy.sh function structure (CDK wrapper)
# ---------------------------------------------------------------------------


class TestDeployFunctions:
    """deploy.sh must contain all CDK wrapper pipeline functions."""

    def test_configure_env_exists(self) -> None:
        assert "configure_env()" in _read(DEPLOY_SCRIPT)

    def test_prepare_install_sh_exists(self) -> None:
        assert "prepare_install_sh()" in _read(DEPLOY_SCRIPT)

    def test_build_web_exists(self) -> None:
        assert "build_web()" in _read(DEPLOY_SCRIPT)

    def test_migrate_legacy_resources_exists(self) -> None:
        assert "migrate_legacy_resources()" in _read(DEPLOY_SCRIPT)

    def test_cdk_deploy_exists(self) -> None:
        assert "cdk_deploy()" in _read(DEPLOY_SCRIPT)


# ---------------------------------------------------------------------------
# CDK stack structure
# ---------------------------------------------------------------------------


class TestCDKStack:
    """CDK stack files must exist with correct structure."""

    def test_cdk_dir_exists(self) -> None:
        assert CDK_DIR.is_dir()

    def test_stack_file_exists(self) -> None:
        assert (CDK_DIR / "lib" / "hyprconf-stack.ts").is_file()

    def test_app_entry_exists(self) -> None:
        assert (CDK_DIR / "bin" / "app.ts").is_file()

    def test_cdk_json_exists(self) -> None:
        assert (CDK_DIR / "cdk.json").is_file()

    def test_package_json_exists(self) -> None:
        assert (CDK_DIR / "package.json").is_file()

    def test_test_file_exists(self) -> None:
        assert (CDK_DIR / "test" / "hyprconf-stack.test.ts").is_file()

    def test_stack_defines_s3_bucket(self) -> None:
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "s3.Bucket" in text

    def test_stack_defines_cloudfront(self) -> None:
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "cloudfront.Distribution" in text

    def test_stack_defines_acm_cert(self) -> None:
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "acm.Certificate" in text

    def test_stack_defines_route53(self) -> None:
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "route53.ARecord" in text

    def test_stack_supports_bucket_import(self) -> None:
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "importBucket" in text
        assert "fromBucketAttributes" in text


# ---------------------------------------------------------------------------
# Web deploy integration
# ---------------------------------------------------------------------------


class TestWebDeployIntegration:
    """Web deploy must be integrated into the CDK pipeline."""

    def test_main_calls_build_web(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "build_web" in text

    def test_web_only_mode(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "web_only" in text or '"web"' in text

    def test_cdk_handles_s3_deployment(self) -> None:
        """CDK stack should handle S3 deployment (not raw aws s3 sync)."""
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "BucketDeployment" in text

    def test_install_sh_no_cache(self) -> None:
        """install.sh must be deployed with no-cache headers."""
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "no-cache" in text

    def test_web_deploy_is_thin_wrapper(self) -> None:
        text = _read(WEB_DEPLOY_SCRIPT)
        assert "infra/deploy.sh" in text
        assert "web" in text


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------


class TestLegacyMigration:
    """deploy.sh must handle migration from pre-CDK resources."""

    def test_detects_existing_bucket(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "head-bucket" in text
        assert "importBucket" in text

    def test_detects_existing_cf_distribution(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "list-distributions" in text

    def test_removes_cname_from_legacy_distribution(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "update-distribution" in text

    def test_checks_cloudformation_stack_exists(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "describe-stacks" in text

    def test_waits_for_propagation(self) -> None:
        text = _read(DEPLOY_SCRIPT)
        assert "Waiting for" in text and "propagat" in text


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
        assert r"\.\w+$" in text or ".w+" in text

    def test_cdk_reads_cf_function(self) -> None:
        """CDK stack must read the CF function source file."""
        text = _read(CDK_DIR / "lib" / "hyprconf-stack.ts")
        assert "cloudfront-function.js" in text
        assert "readFileSync" in text


# ---------------------------------------------------------------------------
# Teardown (CDK-managed)
# ---------------------------------------------------------------------------


class TestTeardown:
    """Teardown must use cdk destroy and clean up remaining resources."""

    def test_teardown_uses_cdk_destroy(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "cdk destroy" in text

    def test_teardown_cleans_up_bucket(self) -> None:
        """Bucket has RETAIN policy, so teardown must explicitly delete it."""
        text = _read(TEARDOWN_SCRIPT)
        assert "delete-bucket" in text

    def test_teardown_cleans_up_legacy_cf_function(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "hyprconf-ua-router" in text

    def test_teardown_requires_confirmation(self) -> None:
        text = _read(TEARDOWN_SCRIPT)
        assert "confirm" in text
        assert "Type the domain" in text
