#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { HyprconfWebStack } from '../lib/hyprconf-web-stack';

const app = new cdk.App();
new HyprconfWebStack(app, 'HyprconfWebStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT || process.env.AWS_ACCOUNT_ID,
    region: 'us-east-1',
  },
});
