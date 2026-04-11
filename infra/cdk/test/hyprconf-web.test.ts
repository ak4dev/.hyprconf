import { describe, it, expect } from 'vitest';
import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { HyprconfWebStack } from '../lib/hyprconf-web-stack';

function createStack(): { stack: HyprconfWebStack; template: Template } {
  const app = new cdk.App({
    context: {
      distributionId: 'E3MPOPCWTB2GDM',
      bucketName: 'hyprconf-sh',
    },
  });
  const stack = new HyprconfWebStack(app, 'TestStack', {
    env: { account: '123456789012', region: 'us-east-1' },
  });
  const template = Template.fromStack(stack);
  return { stack, template };
}

describe('HyprconfWebStack', () => {
  it('synthesizes without error', () => {
    expect(() => createStack()).not.toThrow();
  });

  it('creates a Custom::CDKBucketDeployment resource', () => {
    const { template } = createStack();
    template.hasResource('Custom::CDKBucketDeployment', {});
  });

  it('configures deployment to exclude install.sh', () => {
    const { template } = createStack();
    template.hasResourceProperties('Custom::CDKBucketDeployment', {
      Exclude: Match.arrayWith(['install.sh']),
    });
  });

  it('sets cache invalidation paths to /*', () => {
    const { template } = createStack();
    template.hasResourceProperties('Custom::CDKBucketDeployment', {
      DistributionPaths: ['/*'],
    });
  });

  it('outputs the site URL', () => {
    const { template } = createStack();
    template.hasOutput('SiteUrl', {
      Value: 'https://hyprconf.sh',
    });
  });

  it('outputs the distribution ID', () => {
    const { template } = createStack();
    template.hasOutput('DistributionId', {
      Value: 'E3MPOPCWTB2GDM',
    });
  });

  it('outputs the bucket name', () => {
    const { template } = createStack();
    template.hasOutput('BucketName', {
      Value: 'hyprconf-sh',
    });
  });

  it('does not create a CloudFront Function (managed externally)', () => {
    const { template } = createStack();
    expect(() => {
      template.hasResource('AWS::CloudFront::Function', {});
    }).toThrow();
  });

  it('does not create a new CloudFront distribution', () => {
    const { template } = createStack();
    expect(() => {
      template.hasResource('AWS::CloudFront::Distribution', {});
    }).toThrow();
  });

  it('does not create a new S3 bucket', () => {
    const { template } = createStack();
    expect(() => {
      template.hasResource('AWS::S3::Bucket', {});
    }).toThrow();
  });
});
