import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as path from 'path';
import { Construct } from 'constructs';

export class HyprconfWebStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const bucketName = this.node.tryGetContext('bucketName') ?? 'hyprconf-sh';
    const distributionId = this.node.tryGetContext('distributionId') ?? 'E3MPOPCWTB2GDM';

    const bucket = s3.Bucket.fromBucketName(this, 'Bucket', bucketName);

    // Import existing distribution for cache invalidation only.
    // The distribution itself (behaviors, function associations) is managed
    // by the deploy script via AWS CLI — CDK cannot modify imported distributions.
    const distribution = cloudfront.Distribution.fromDistributionAttributes(
      this,
      'Distribution',
      { distributionId, domainName: 'hyprconf.sh' },
    );

    // Deploy web/dist/ to S3 (excludes install.sh which is managed separately)
    new s3deploy.BucketDeployment(this, 'DeployWeb', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', '..', '..', 'web', 'dist'))],
      destinationBucket: bucket,
      distribution,
      distributionPaths: ['/*'],
      exclude: ['install.sh'],
    });

    new cdk.CfnOutput(this, 'BucketName', {
      value: bucketName,
      description: 'S3 bucket hosting the website',
    });

    new cdk.CfnOutput(this, 'DistributionId', {
      value: distributionId,
      description: 'CloudFront distribution ID',
    });

    new cdk.CfnOutput(this, 'SiteUrl', {
      value: 'https://hyprconf.sh',
    });
  }
}
