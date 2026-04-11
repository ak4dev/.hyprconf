#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CF_FUNCTION_NAME="hyprconf-ua-router"
CF_FUNCTION_FILE="$REPO_ROOT/infra/cloudfront-function.js"

# ── 0. Resolve AWS account ─────────────────────────────────────────
echo "▸ Resolving AWS identity…"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_ACCOUNT="$ACCOUNT_ID"
CDK_REGION="us-east-1"
echo "  Account: $ACCOUNT_ID  Region: $CDK_REGION"

# ── 1. Build web frontend ──────────────────────────────────────────
echo "▸ Building web frontend…"
cd "$REPO_ROOT/web"
npm run build

# ── 2. Bootstrap CDK (idempotent) ──────────────────────────────────
echo "▸ Ensuring CDK is bootstrapped…"
cd "$REPO_ROOT/infra/cdk"
npm install --silent
npx cdk bootstrap "aws://$ACCOUNT_ID/$CDK_REGION" --quiet 2>/dev/null || true

# ── 3. Deploy assets to S3 via CDK ─────────────────────────────────
echo "▸ Deploying assets via CDK…"
npx cdk deploy --require-approval never --outputs-file cdk-outputs.json

# ── 4. Ensure bucket policy allows CloudFront to read all objects ──
echo "▸ Updating S3 bucket policy…"
BUCKET_NAME="hyprconf-sh"
cat > /tmp/hyprconf-bucket-policy.json <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadAllObjects",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    }
  ]
}
POLICY
aws s3api put-bucket-policy --bucket "$BUCKET_NAME" --policy file:///tmp/hyprconf-bucket-policy.json --region "$CDK_REGION"
rm -f /tmp/hyprconf-bucket-policy.json

# ── 5. Update CloudFront Function ──────────────────────────────────
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
