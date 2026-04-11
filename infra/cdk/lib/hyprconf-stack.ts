import * as path from "path";
import * as fs from "fs";
import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as route53Targets from "aws-cdk-lib/aws-route53-targets";
import { Construct } from "constructs";

export interface HyprconfStackProps extends cdk.StackProps {
  /** Domain name (e.g. hyprconf.sh) */
  domain: string;
  /** S3 bucket name */
  bucketName: string;
  /** Route53 hosted zone ID */
  hostedZoneId: string;
  /** GitHub repo URL injected into install.sh */
  repoUrl: string;
}

export class HyprconfStack extends cdk.Stack {
  public readonly bucket: s3.IBucket;
  public readonly distribution: cloudfront.Distribution;

  constructor(scope: Construct, id: string, props: HyprconfStackProps) {
    super(scope, id, props);

    const repoRoot = path.resolve(__dirname, "..", "..", "..");
    const webDistDir = path.join(repoRoot, "web", "dist");
    const installSrc = path.join(repoRoot, "install", "install.sh");
    const cfFnSrc = path.join(__dirname, "..", "..", "cloudfront-function.js");

    // ── S3 Bucket ──────────────────────────────────────────────────────────
    // Import existing bucket if it already exists, or create new.
    // Public-read is required so `curl hyprconf.sh | bash` works without CF.
    // On first deploy CDK creates the bucket. On subsequent deploys with an
    // existing bucket (created by the legacy deploy.sh), we import it.
    const importExisting = this.node.tryGetContext("importBucket") === "true";

    if (importExisting) {
      this.bucket = s3.Bucket.fromBucketAttributes(
        this,
        "SiteBucket",
        {
          bucketName: props.bucketName,
          bucketWebsiteUrl: `http://${props.bucketName}.s3-website.${this.region}.amazonaws.com`,
        }
      );
    } else {
      this.bucket = new s3.Bucket(this, "SiteBucket", {
        bucketName: props.bucketName,
        publicReadAccess: true,
        blockPublicAccess: new s3.BlockPublicAccess({
          blockPublicAcls: false,
          ignorePublicAcls: false,
          blockPublicPolicy: false,
          restrictPublicBuckets: false,
        }),
        removalPolicy: cdk.RemovalPolicy.RETAIN,
        websiteIndexDocument: "index.html",
        objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
      });
    }

    // ── ACM Certificate (must be us-east-1 for CloudFront) ─────────────────
    const zone = route53.HostedZone.fromHostedZoneAttributes(
      this,
      "HostedZone",
      {
        zoneName: this.extractZoneName(props.domain),
        hostedZoneId: props.hostedZoneId,
      }
    );

    const certificate = new acm.Certificate(this, "Certificate", {
      domainName: props.domain,
      validation: acm.CertificateValidation.fromDns(zone),
    });

    // ── CloudFront Function (UA-based routing) ─────────────────────────────
    const cfFunctionCode = fs.readFileSync(cfFnSrc, "utf-8");
    const uaRouter = new cloudfront.Function(this, "UaRouterFunction", {
      code: cloudfront.FunctionCode.fromInline(cfFunctionCode),
      runtime: cloudfront.FunctionRuntime.JS_2_0,
      comment: `UA routing for ${props.domain}`,
    });

    // ── CloudFront Distribution ────────────────────────────────────────────
    // Use S3StaticWebsiteOrigin — bucket has public-read and website hosting
    // enabled so curl can fetch install.sh directly from S3.
    const s3Origin = new origins.S3StaticWebsiteOrigin(this.bucket);

    this.distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultBehavior: {
        origin: s3Origin,
        viewerProtocolPolicy:
          cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        compress: true,
        functionAssociations: [
          {
            function: uaRouter,
            eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
          },
        ],
      },
      domainNames: [props.domain],
      certificate,
      defaultRootObject: "index.html",
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
      comment: `hyprconf install + web — ${props.domain}`,
    });

    // ── Route53 A-Record ───────────────────────────────────────────────────
    new route53.ARecord(this, "AliasRecord", {
      zone,
      recordName: props.domain,
      target: route53.RecordTarget.fromAlias(
        new route53Targets.CloudFrontTarget(this.distribution)
      ),
    });

    // ── Deploy web assets ──────────────────────────────────────────────────
    // Web dist must be pre-built by the wrapper script before cdk deploy.
    if (fs.existsSync(webDistDir)) {
      new s3deploy.BucketDeployment(this, "WebAssets", {
        sources: [s3deploy.Source.asset(webDistDir)],
        destinationBucket: this.bucket,
        distribution: this.distribution,
        distributionPaths: ["/*"],
        cacheControl: [
          s3deploy.CacheControl.fromString(
            "public, max-age=31536000, immutable"
          ),
        ],
        exclude: ["install.sh"],
        prune: false, // don't delete install.sh
      });
    }

    // ── Deploy install.sh separately with no-cache ─────────────────────────
    // The wrapper script (deploy.sh) creates install.sh.deploy with the
    // fork's repo URL injected. Use that if available, otherwise use the
    // original install.sh.
    const installDeploy = path.join(
      repoRoot,
      "install",
      "install.sh.deploy"
    );
    const installFile = fs.existsSync(installDeploy)
      ? installDeploy
      : installSrc;
    if (fs.existsSync(installFile)) {
      new s3deploy.BucketDeployment(this, "InstallScript", {
        sources: [
          s3deploy.Source.asset(path.dirname(installFile), {
            exclude: [
              "*",
              "!" + path.basename(installFile),
            ],
          }),
        ],
        destinationBucket: this.bucket,
        destinationKeyPrefix: "",
        cacheControl: [
          s3deploy.CacheControl.fromString("no-cache, no-store"),
        ],
        contentType: "text/plain; charset=utf-8",
        prune: false,
      });
    }

    // ── Outputs ────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, "SiteUrl", {
      value: `https://${props.domain}`,
      description: "hyprconf site URL",
    });
    new cdk.CfnOutput(this, "DistributionId", {
      value: this.distribution.distributionId,
      description: "CloudFront distribution ID",
    });
    new cdk.CfnOutput(this, "DistributionDomain", {
      value: this.distribution.distributionDomainName,
      description: "CloudFront distribution domain",
    });
    new cdk.CfnOutput(this, "BucketName", {
      value: this.bucket.bucketName,
      description: "S3 bucket name",
    });
    new cdk.CfnOutput(this, "InstallCommand", {
      value: `bash <(curl -fsSL https://${props.domain})`,
      description: "One-liner install command",
    });
  }

  /**
   * Extract the parent zone name from a domain.
   * e.g. "hyprconf.sh" -> "hyprconf.sh", "get.example.com" -> "example.com"
   */
  private extractZoneName(domain: string): string {
    const parts = domain.split(".");
    if (parts.length <= 2) return domain;
    return parts.slice(1).join(".");
  }
}
