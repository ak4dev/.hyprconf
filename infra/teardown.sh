#!/usr/bin/env bash
#
#  infra/teardown.sh — destroy all AWS resources created by deploy.sh
#
#  Usage:
#    bash infra/teardown.sh
#
#  Sources configuration from ~/.config/hyprconf/infra.env (written by
#  'hyprconf deploy') and reads resource identifiers from
#  ~/.config/hyprconf/deploy-state.
#  Requires typing the domain name to confirm before proceeding.
#
#  Note: CloudFront distributions must be disabled before deletion.
#  Disabling takes 5–15 minutes to propagate. If deletion fails,
#  wait a few minutes and re-run — the script is safe to retry.

set -euo pipefail

INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Config and state live outside the repo (same paths as deploy.sh)
CFG_DIR="$HOME/.config/hyprconf"
CFG_FILE="$CFG_DIR/infra.env"
STATE_FILE="$CFG_DIR/deploy-state"

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
log_die()  { printf '%s  ✘ FATAL: %s%s%s\n' "$GL" "$WH" "$1" "$RS" >&2; exit 1; }

state_get() { grep "^${1}=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || true; }

# ── Destructive-operation confirmation ───────────────────────────────────────
confirm() {
  printf '\n%s  ⚠  This will permanently destroy ALL hyprconf AWS resources:%s\n' "$GL" "$RS"
  printf '%s     Domain:   %s%s\n'   "$DM" "$HYPRCONF_DOMAIN" "$RS"
  printf '%s     Bucket:   %s%s\n'   "$DM" "$HYPRCONF_BUCKET"  "$RS"
  local dist_id; dist_id="$(state_get DISTRIBUTION_ID)"
  [[ -n "$dist_id" ]] && printf '%s     CloudFront: %s%s\n' "$DM" "$dist_id" "$RS"
  local cert_arn; cert_arn="$(state_get CERT_ARN)"
  [[ -n "$cert_arn" ]] && printf '%s     Cert ARN:   %s%s\n' "$DM" "$cert_arn" "$RS"
  printf '\n%s  Type the domain name to confirm: %s' "$GL" "$RS"
  local input; read -r input
  [[ "$input" == "$HYPRCONF_DOMAIN" ]] \
    || log_die "Confirmation mismatch — aborting."
  printf '\n'
}

# ── Step 1: Route53 record ────────────────────────────────────────────────────
teardown_dns() {
  local dist_domain; dist_domain="$(state_get DISTRIBUTION_DOMAIN)"
  if [[ -z "$dist_domain" ]]; then
    log_warn "No distribution domain in state — skipping DNS removal."
    return
  fi
  log_step "Removing Route53 record for $HYPRCONF_DOMAIN ..."
  aws route53 change-resource-record-sets \
    --hosted-zone-id "$HYPRCONF_ZONE_ID" \
    --change-batch "{
      \"Changes\": [{
        \"Action\": \"DELETE\",
        \"ResourceRecordSet\": {
          \"Name\": \"$HYPRCONF_DOMAIN\",
          \"Type\": \"A\",
          \"AliasTarget\": {
            \"HostedZoneId\": \"Z2FDTNDATAQYW2\",
            \"DNSName\": \"$dist_domain\",
            \"EvaluateTargetHealth\": false
          }
        }
      }]
    }" --output text > /dev/null 2>&1 \
    || log_warn "Route53 record not found (already removed?)."
  log_ok "DNS record removed."
}

# ── Step 2: CloudFront distribution ──────────────────────────────────────────
teardown_cdn() {
  local dist_id; dist_id="$(state_get DISTRIBUTION_ID)"
  if [[ -z "$dist_id" ]]; then
    log_warn "No distribution ID in state — skipping."
    return
  fi

  log_step "Disabling CloudFront distribution $dist_id ..."
  local etag cfg status
  etag=$(aws cloudfront get-distribution-config --id "$dist_id" \
    --query 'ETag' --output text 2>/dev/null || true)
  if [[ -z "$etag" ]]; then
    log_warn "Distribution not found (already deleted?)."
    return
  fi

  # Check current status
  status=$(aws cloudfront get-distribution --id "$dist_id" \
    --query 'Distribution.Status' --output text)

  if [[ "$status" == "Deployed" ]]; then
    cfg=$(aws cloudfront get-distribution-config --id "$dist_id" \
      --query 'DistributionConfig' --output json)
    # Flip Enabled to false
    cfg=$(printf '%s' "$cfg" | sed 's/"Enabled": true/"Enabled": false/')
    etag=$(aws cloudfront update-distribution --id "$dist_id" \
      --if-match "$etag" --distribution-config "$cfg" \
      --query 'ETag' --output text)
    log_ok "Distribution disabled. Waiting for propagation..."

    # Poll until status returns to Deployed (disabled state)
    local attempts=0
    while [[ $attempts -lt 30 ]]; do
      sleep 30
      status=$(aws cloudfront get-distribution --id "$dist_id" \
        --query 'Distribution.Status' --output text)
      [[ "$status" == "Deployed" ]] && break
      (( attempts++ ))
      log_step "Still propagating... ($((attempts * 30))s)"
    done
  fi

  etag=$(aws cloudfront get-distribution-config --id "$dist_id" \
    --query 'ETag' --output text)
  aws cloudfront delete-distribution --id "$dist_id" --if-match "$etag" \
    --output text > /dev/null 2>&1 \
    || { log_warn "Distribution not yet deletable. Wait a few minutes and re-run teardown.sh."; return; }
  log_ok "Distribution deleted."
}

# ── Step 3: ACM certificate ───────────────────────────────────────────────────
teardown_cert() {
  local cert_arn; cert_arn="$(state_get CERT_ARN)"
  if [[ -z "$cert_arn" ]]; then
    log_warn "No certificate ARN in state — skipping."
    return
  fi

  # Remove the validation CNAME from Route53 before deleting the cert.
  # Once the cert is gone, ACM no longer exposes the record details.
  log_step "Removing ACM validation CNAME from Route53 ..."
  local rec_name rec_value
  rec_name=$(aws acm describe-certificate --certificate-arn "$cert_arn" \
    --region us-east-1 \
    --query 'Certificate.DomainValidationOptions[0].ResourceRecord.Name' \
    --output text 2>/dev/null || true)
  rec_value=$(aws acm describe-certificate --certificate-arn "$cert_arn" \
    --region us-east-1 \
    --query 'Certificate.DomainValidationOptions[0].ResourceRecord.Value' \
    --output text 2>/dev/null || true)

  if [[ -n "$rec_name" && "$rec_name" != "None" && -n "$rec_value" ]]; then
    aws route53 change-resource-record-sets \
      --hosted-zone-id "$HYPRCONF_ZONE_ID" \
      --change-batch "$(printf '{"Changes":[{"Action":"DELETE","ResourceRecordSet":{"Name":"%s","Type":"CNAME","TTL":60,"ResourceRecords":[{"Value":"%s"}]}}]}' \
        "$rec_name" "$rec_value")" \
      --output text > /dev/null 2>&1 \
      && log_ok "Validation CNAME removed." \
      || log_warn "Validation CNAME not found (already removed?)."
  else
    log_warn "Could not retrieve validation CNAME details — may need manual cleanup."
  fi

  log_step "Deleting ACM certificate $cert_arn ..."
  aws acm delete-certificate --certificate-arn "$cert_arn" \
    --region us-east-1 --output text > /dev/null 2>&1 \
    || log_warn "Certificate not found (already deleted?)."
  log_ok "Certificate deleted."
}

# ── Step 4: S3 bucket ─────────────────────────────────────────────────────────
teardown_bucket() {
  if [[ -z "${HYPRCONF_BUCKET:-}" ]]; then
    log_warn "HYPRCONF_BUCKET not set — skipping bucket removal."
    return
  fi
  log_step "Emptying s3://$HYPRCONF_BUCKET ..."
  aws s3 rm "s3://$HYPRCONF_BUCKET" --recursive --output text > /dev/null 2>&1 || true
  log_step "Deleting bucket..."
  aws s3api delete-bucket --bucket "$HYPRCONF_BUCKET" --output text > /dev/null 2>&1 \
    || log_warn "Bucket not found (already deleted?)."
  log_ok "Bucket deleted."
}

# ── Entry ─────────────────────────────────────────────────────────────────────
main() {
  # shellcheck source=../assets/banner.sh
  source "$INFRA_DIR/../assets/banner.sh" 2>/dev/null || true
  print_banner

  [[ -f "$CFG_FILE" ]] \
    || log_die "~/.config/hyprconf/infra.env not found. Run 'hyprconf deploy' first."
  command -v aws &>/dev/null || log_die "AWS CLI not found."
  aws sts get-caller-identity --output text --query 'Account' &>/dev/null \
    || log_die "AWS authentication failed."

  confirm
  teardown_dns
  teardown_cdn
  teardown_cert
  teardown_bucket

  rm -f "$STATE_FILE"
  printf '\n%s  ✔ Teardown complete. All hyprconf AWS resources removed.%s\n\n' "$GR" "$RS"
}

main "$@"
