#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CF_FUNCTION_NAME="hyprconf-ua-router"
CF_FUNCTION_FILE="$REPO_ROOT/infra/cloudfront-function.js"

# ── 1. Build web frontend ──────────────────────────────────────────
echo "▸ Building web frontend…"
cd "$REPO_ROOT/web"
npm run build

# ── 2. Deploy assets to S3 via CDK ─────────────────────────────────
echo "▸ Deploying assets via CDK…"
cd "$REPO_ROOT/infra/cdk"
npm install --silent
npx cdk deploy --require-approval never --outputs-file cdk-outputs.json

# ── 3. Update CloudFront Function ──────────────────────────────────
echo "▸ Updating CloudFront Function ($CF_FUNCTION_NAME)…"

# Get current ETag (required for update)
ETAG=$(aws cloudfront describe-function \
  --name "$CF_FUNCTION_NAME" \
  --query 'ETag' --output text 2>/dev/null || echo "")

if [ -z "$ETAG" ] || [ "$ETAG" = "None" ]; then
  echo "  Creating new CloudFront Function…"
  aws cloudfront create-function \
    --name "$CF_FUNCTION_NAME" \
    --function-config "Comment=UA routing for hyprconf.sh,Runtime=cloudfront-js-2.0" \
    --function-code "fileb://$CF_FUNCTION_FILE"
else
  echo "  Updating existing function (ETag: $ETAG)…"
  aws cloudfront update-function \
    --name "$CF_FUNCTION_NAME" \
    --if-match "$ETAG" \
    --function-config "Comment=UA routing for hyprconf.sh,Runtime=cloudfront-js-2.0" \
    --function-code "fileb://$CF_FUNCTION_FILE"
fi

# Publish the function (move from DEVELOPMENT to LIVE stage)
echo "▸ Publishing CloudFront Function…"
DEV_ETAG=$(aws cloudfront describe-function \
  --name "$CF_FUNCTION_NAME" --stage DEVELOPMENT \
  --query 'ETag' --output text)

aws cloudfront publish-function \
  --name "$CF_FUNCTION_NAME" \
  --if-match "$DEV_ETAG"

echo "✓ Deployed to https://hyprconf.sh"
