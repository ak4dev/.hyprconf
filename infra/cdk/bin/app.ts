#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { HyprconfWebStack } from '../lib/hyprconf-web-stack';

const app = new cdk.App();
new HyprconfWebStack(app, 'HyprconfWebStack', {
  env: { account: '390844779058', region: 'us-east-1' },
});
