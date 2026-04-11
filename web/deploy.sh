#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "▸ Building web frontend…"
cd "$REPO_ROOT/web"
npm run build

echo "▸ Deploying via CDK…"
cd "$REPO_ROOT/infra/cdk"
npx cdk deploy --require-approval never

echo "✓ Deployed to https://hyprconf.sh"
