#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { HyprconfStack } from "../lib/hyprconf-stack";

const app = new cdk.App();

const domain = app.node.tryGetContext("domain") || process.env.HYPRCONF_DOMAIN;
const bucket = app.node.tryGetContext("bucket") || process.env.HYPRCONF_BUCKET;
const zoneId = app.node.tryGetContext("zoneId") || process.env.HYPRCONF_ZONE_ID;

if (!domain || !bucket || !zoneId) {
  console.error(
    "Missing required context. Provide via environment or --context:\n" +
      "  HYPRCONF_DOMAIN / -c domain=...\n" +
      "  HYPRCONF_BUCKET / -c bucket=...\n" +
      "  HYPRCONF_ZONE_ID / -c zoneId=...\n"
  );
  process.exit(1);
}

new HyprconfStack(app, "HyprconfStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.AWS_DEFAULT_REGION || "us-east-1",
  },
  domain,
  bucketName: bucket,
  hostedZoneId: zoneId,
});
