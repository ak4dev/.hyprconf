import { describe, it, expect } from 'vitest';
import * as cdk from 'aws-cdk-lib';
import { HyprconfWebStack } from '../lib/hyprconf-web-stack';

describe('HyprconfWebStack', () => {
  it('synthesizes without error', () => {
    const app = new cdk.App({
      context: {
        distributionId: 'E3MPOPCWTB2GDM',
        bucketName: 'hyprconf-sh',
      },
    });
    expect(() => {
      new HyprconfWebStack(app, 'TestStack', {
        env: { account: '390844779058', region: 'us-east-1' },
      });
    }).not.toThrow();
  });

  it('contains CloudFront Function', () => {
    const app = new cdk.App({
      context: {
        distributionId: 'E3MPOPCWTB2GDM',
        bucketName: 'hyprconf-sh',
      },
    });
    const stack = new HyprconfWebStack(app, 'TestStack', {
      env: { account: '390844779058', region: 'us-east-1' },
    });
    const template = cdk.assertions.Template.fromStack(stack);
    template.hasResourceProperties('AWS::CloudFront::Function', {
      FunctionConfig: {
        Runtime: 'cloudfront-js-2.0',
      },
    });
  });
});
