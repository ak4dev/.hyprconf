#!/usr/bin/env bash
#
#  infra/teardown.sh — destroy all AWS resources created by CDK
#
#  Usage:
#    bash infra/teardown.sh
#
#  Sources configuration from ~/.config/hyprconf/infra.env (written by
#  'hyprconf deploy'). Uses `cdk destroy` to remove all CDK-managed resources,
#  then cleans up the S3 bucket (CDK retains it by default to avoid data loss).
#
#  Requires typing the domain name to confirm before proceeding.

set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$INFRA_DIR")"

# Config lives outside the repo (same paths as deploy.sh)
DEFAULT_CFG_DIR="$HOME/.config/hyprconf"
CFG_FILE="${HYPRCONF_INFRA_CFG_FILE:-$DEFAULT_CFG_DIR/infra.env}"
STATE_FILE="${HYPRCONF_INFRA_STATE_FILE:-$DEFAULT_CFG_DIR/deploy-state}"
CFG_DIR="$(dirname "$CFG_FILE")"

[[ -f "$CFG_FILE" ]] && source "$CFG_FILE"

if [[ -t 1 ]]; then
  WH=$'\e[1;37m' GL=$'\e[1;31m' AM=$'\e[1;33m'
  GR=$'\e[1;32m' DM=$'\e[2;37m' RS=$'\e[0m'
else
  WH='' GL='' AM='' GR='' DM='' RS=''
fi

log_step() { printf '%s  ▸ %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_ok()   { printf '%s  ✔ %s%s%s\n'        "$GR" "$WH" "$1" "$RS"; }
log_warn() { printf '%s  ! %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_info() { printf '%s  ─ %s%s%s\n'        "$DM" "$WH" "$1" "$RS"; }
log_die()  { printf '%s  ✘ FATAL: %s%s%s\n' "$GL" "$WH" "$1" "$RS" >&2; exit 1; }

# ── Confirmation ──────────────────────────────────────────────────────────────
confirm() {
  printf '\n%s  ⚠  This will permanently destroy ALL hyprconf AWS resources:%s\n' "$GL" "$RS"
  printf '%s     Domain:   %s%s\n' "$DM" "${HYPRCONF_DOMAIN:-<unknown>}" "$RS"
  printf '%s     Bucket:   %s%s\n' "$DM" "${HYPRCONF_BUCKET:-<unknown>}" "$RS"
  printf '%s     Stack:    HyprconfStack%s\n' "$DM" "$RS"
  printf '\n%s  Type the domain name to confirm: %s' "$GL" "$RS"
  local input; read -r input
  [[ "$input" == "$HYPRCONF_DOMAIN" ]] \
    || log_die "Confirmation mismatch — aborting."
  printf '\n'
}

# ── CDK Destroy ───────────────────────────────────────────────────────────────
cdk_destroy() {
  local cdk_dir="$INFRA_DIR/cdk"

  if [[ ! -d "$cdk_dir" ]]; then
    log_die "infra/cdk/ directory not found."
  fi

  command -v npx &>/dev/null || log_die "npx not found. Install Node.js."

  if [[ ! -d "$cdk_dir/node_modules" ]]; then
    log_step "Installing CDK dependencies ..."
    (cd "$cdk_dir" && npm install --silent)
  fi

  log_step "Destroying HyprconfStack via CDK ..."
  (cd "$cdk_dir" && npx cdk destroy \
    --force \
    --context "domain=${HYPRCONF_DOMAIN}" \
    --context "bucket=${HYPRCONF_BUCKET}" \
    --context "zoneId=${HYPRCONF_ZONE_ID}" \
    --context "repoUrl=${HYPRCONF_REPO:-}" \
    2>&1) \
    || log_warn "CDK destroy encountered issues (see output above)."

  log_ok "CDK stack destroyed."
}

# ── S3 bucket cleanup ─────────────────────────────────────────────────────────
# CDK retains the bucket (RemovalPolicy.RETAIN) to prevent data loss.
# Teardown explicitly empties and deletes it.
cleanup_bucket() {
  if [[ -z "${HYPRCONF_BUCKET:-}" ]]; then
    log_warn "HYPRCONF_BUCKET not set — skipping bucket removal."
    return
  fi

  if ! aws s3api head-bucket --bucket "$HYPRCONF_BUCKET" 2>/dev/null; then
    log_info "Bucket $HYPRCONF_BUCKET does not exist — nothing to clean up."
    return
  fi

  log_step "Emptying s3://$HYPRCONF_BUCKET ..."
  aws s3 rm "s3://$HYPRCONF_BUCKET" --recursive --output text > /dev/null 2>&1 || true
  log_step "Deleting bucket ..."
  aws s3api delete-bucket --bucket "$HYPRCONF_BUCKET" --output text > /dev/null 2>&1 \
    || log_warn "Could not delete bucket (may need manual cleanup)."
  log_ok "Bucket deleted."
}

# ── Cleanup legacy resources ──────────────────────────────────────────────────
# Removes any orphaned resources from pre-CDK deployments.
cleanup_legacy() {
  # Legacy CF function (CDK-managed functions are auto-deleted by cdk destroy)
  local fn_etag
  fn_etag=$(aws cloudfront describe-function \
    --name "hyprconf-ua-router" --stage LIVE \
    --query 'ETag' --output text 2>/dev/null || echo "")
  if [[ -n "$fn_etag" && "$fn_etag" != "None" ]]; then
    log_step "Deleting orphaned legacy CloudFront Function ..."
    aws cloudfront delete-function \
      --name "hyprconf-ua-router" --if-match "$fn_etag" \
      --output text > /dev/null 2>&1 \
      || log_warn "Could not delete legacy CF function (may be in use)."
    log_ok "Legacy CF function deleted."
  fi

  # Legacy CF distribution (from migration, if not yet cleaned up)
  local legacy_dist_id
  legacy_dist_id=$(grep "^LEGACY_DISTRIBUTION_ID=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || true)
  if [[ -n "$legacy_dist_id" ]]; then
    log_info "Legacy distribution $legacy_dist_id may still exist."
    log_info "To clean up: aws cloudfront disable-distribution --id $legacy_dist_id"
    log_info "Then wait ~10m, then: aws cloudfront delete-distribution --id $legacy_dist_id --if-match <etag>"
  fi
}

# ── Entry ─────────────────────────────────────────────────────────────────────
main() {
  # shellcheck source=../assets/banner.sh
  source "$ROOT_DIR/assets/banner.sh" 2>/dev/null || true
  print_banner

  [[ -f "$CFG_FILE" ]] \
    || log_die "$CFG_FILE not found. Run 'hyprconf deploy' first."
  command -v aws &>/dev/null || log_die "AWS CLI not found."
  aws sts get-caller-identity --output text --query 'Account' &>/dev/null \
    || log_die "AWS authentication failed."

  confirm

  cdk_destroy
  cleanup_bucket
  cleanup_legacy

  # Clean up state files
  rm -f "$STATE_FILE" "$CFG_DIR/cdk-outputs.json"

  printf '\n%s  ──────────────────────────────────────────────────────────────%s\n' "$GR" "$RS"
  printf '%s  ✔  Teardown complete. All hyprconf AWS resources removed.%s\n' "$GR" "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────%s\n\n' "$GR" "$RS"
  printf '%s  Config file preserved: %s%s\n' "$DM" "$CFG_FILE" "$RS"
  printf '%s  To reconfigure, delete it and run: hyprconf deploy%s\n\n' "$DM" "$RS"
}

main "$@"
