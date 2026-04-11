#!/usr/bin/env bash
# Thin wrapper — delegates to the integrated deploy pipeline.
# Usage: ./web/deploy.sh        (web-only quick deploy)
#    or: hyprconf deploy web    (equivalent via the CLI)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec bash "$REPO_ROOT/infra/deploy.sh" web
