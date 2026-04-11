import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as path from 'path';
import { Construct } from 'constructs';

/** CloudFront Function: UA-based routing (curl→install.sh, browsers→SPA) */
const CF_FUNCTION_CODE = `
function handler(event) {
  var request = event.request;
  var ua = (request.headers["user-agent"] || {value: ""}).value;
  if (/curl|wget/i.test(ua)) {
    request.uri = "/install.sh";
    return request;
  }
  if (request.uri === "/" || !/\\.\\w+$/.test(request.uri)) {
    request.uri = "/index.html";
  }
  return request;
}
`.trim();

export class HyprconfWebStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const bucketName = this.node.tryGetContext('bucketName') ?? 'hyprconf-sh';
    const distributionId = this.node.tryGetContext('distributionId') ?? 'E3MPOPCWTB2GDM';

    // Import existing bucket
    const bucket = s3.Bucket.fromBucketName(this, 'Bucket', bucketName);

    // Import existing distribution (for cache invalidation reference)
    const distribution = cloudfront.Distribution.fromDistributionAttributes(
      this,
      'Distribution',
      {
        distributionId,
        domainName: 'hyprconf.sh',
      }
    );

    // CloudFront Function — managed by CDK
    const cfFunction = new cloudfront.Function(this, 'UaRouter', {
      functionName: 'hyprconf-ua-router',
      code: cloudfront.FunctionCode.fromInline(CF_FUNCTION_CODE),
      runtime: cloudfront.FunctionRuntime.JS_2_0,
      comment: 'Routes curl/wget to install.sh, browsers to React SPA',
    });

    // Deploy web/dist/ to S3 (excludes install.sh which is managed separately)
    new s3deploy.BucketDeployment(this, 'DeployWeb', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '../../..', 'web', 'dist'))],
      destinationBucket: bucket,
      distribution,
      distributionPaths: ['/*'],
      exclude: ['install.sh'],
    });

    // Outputs
    new cdk.CfnOutput(this, 'FunctionArn', {
      value: cfFunction.functionArn,
      description: 'CloudFront Function ARN',
    });

    new cdk.CfnOutput(this, 'SiteUrl', {
      value: 'https://hyprconf.sh',
    });
  }
}
