import { describe, it, expect } from "vitest";
import * as cdk from "aws-cdk-lib";
import { Template, Match } from "aws-cdk-lib/assertions";
import { HyprconfStack } from "../lib/hyprconf-stack";

function createStack(overrides?: { importBucket?: boolean }): Template {
  const app = new cdk.App({
    context: {
      ...(overrides?.importBucket ? { importBucket: "true" } : {}),
    },
  });
  const stack = new HyprconfStack(app, "TestStack", {
    env: { account: "123456789012", region: "us-east-1" },
    domain: "test.example.com",
    bucketName: "test-example-com",
    hostedZoneId: "Z0123456789ABCDEFGHIJ",
  });
  return Template.fromStack(stack);
}

describe("HyprconfStack", () => {
  describe("S3 Bucket", () => {
    it("creates a bucket with the specified name", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::S3::Bucket", {
        BucketName: "test-example-com",
      });
    });

    it("configures public access", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::S3::Bucket", {
        PublicAccessBlockConfiguration: {
          BlockPublicAcls: false,
          IgnorePublicAcls: false,
          BlockPublicPolicy: false,
          RestrictPublicBuckets: false,
        },
      });
    });

    it("retains bucket on stack deletion", () => {
      const template = createStack();
      const buckets = template.findResources("AWS::S3::Bucket");
      const bucketKeys = Object.keys(buckets);
      // At least one bucket should have RETAIN
      const hasRetain = bucketKeys.some(
        (key) => buckets[key].DeletionPolicy === "Retain"
      );
      expect(hasRetain).toBe(true);
    });
  });

  describe("ACM Certificate", () => {
    it("creates a certificate for the domain", () => {
      const template = createStack();
      template.hasResourceProperties(
        "AWS::CertificateManager::Certificate",
        {
          DomainName: "test.example.com",
          ValidationMethod: "DNS",
        }
      );
    });
  });

  describe("CloudFront Distribution", () => {
    it("creates a distribution with the custom domain", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::CloudFront::Distribution", {
        DistributionConfig: Match.objectLike({
          Aliases: ["test.example.com"],
          DefaultRootObject: "index.html",
          PriceClass: "PriceClass_100",
          Enabled: true,
        }),
      });
    });

    it("enforces HTTPS redirect", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::CloudFront::Distribution", {
        DistributionConfig: Match.objectLike({
          DefaultCacheBehavior: Match.objectLike({
            ViewerProtocolPolicy: "redirect-to-https",
            Compress: true,
          }),
        }),
      });
    });

    it("associates the UA router function", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::CloudFront::Distribution", {
        DistributionConfig: Match.objectLike({
          DefaultCacheBehavior: Match.objectLike({
            FunctionAssociations: Match.arrayWith([
              Match.objectLike({
                EventType: "viewer-request",
              }),
            ]),
          }),
        }),
      });
    });

    it("uses TLS 1.2 minimum", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::CloudFront::Distribution", {
        DistributionConfig: Match.objectLike({
          ViewerCertificate: Match.objectLike({
            MinimumProtocolVersion: "TLSv1.2_2021",
            SslSupportMethod: "sni-only",
          }),
        }),
      });
    });
  });

  describe("CloudFront Function", () => {
    it("creates the UA router function", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::CloudFront::Function", {
        FunctionConfig: Match.objectLike({
          Runtime: "cloudfront-js-2.0",
        }),
      });
    });

    it("includes routing logic for curl", () => {
      const template = createStack();
      const fns = template.findResources("AWS::CloudFront::Function");
      const fnKeys = Object.keys(fns);
      expect(fnKeys.length).toBeGreaterThan(0);
      const fnCode =
        fns[fnKeys[0]].Properties?.FunctionCode || "";
      expect(fnCode).toContain("curl");
      expect(fnCode).toContain("install.sh");
      expect(fnCode).toContain("index.html");
    });
  });

  describe("Route53 Record", () => {
    it("creates an A record for the domain", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::Route53::RecordSet", {
        Name: "test.example.com.",
        Type: "A",
      });
    });

    it("aliases to the CloudFront distribution", () => {
      const template = createStack();
      template.hasResourceProperties("AWS::Route53::RecordSet", {
        AliasTarget: Match.objectLike({
          DNSName: Match.anyValue(),
          HostedZoneId: Match.anyValue(),
        }),
      });
    });
  });

  describe("Stack Outputs", () => {
    it("outputs the site URL", () => {
      const template = createStack();
      const outputs = template.toJSON().Outputs || {};
      const siteUrl = Object.values(outputs).find(
        (o: any) => o.Description === "hyprconf site URL"
      ) as any;
      expect(siteUrl).toBeDefined();
      expect(siteUrl.Value).toBe("https://test.example.com");
    });

    it("outputs the distribution ID", () => {
      const template = createStack();
      const outputs = template.toJSON().Outputs || {};
      const distId = Object.values(outputs).find(
        (o: any) => o.Description === "CloudFront distribution ID"
      ) as any;
      expect(distId).toBeDefined();
    });

    it("outputs the install command", () => {
      const template = createStack();
      const outputs = template.toJSON().Outputs || {};
      const cmd = Object.values(outputs).find(
        (o: any) => o.Description === "One-liner install command"
      ) as any;
      expect(cmd).toBeDefined();
      expect(cmd.Value).toContain("test.example.com");
    });
  });

  describe("Import existing bucket", () => {
    it("does not create an S3 bucket when importBucket is true", () => {
      const template = createStack({ importBucket: true });
      template.resourceCountIs("AWS::S3::Bucket", 0);
    });

    it("still creates CloudFront distribution when importing bucket", () => {
      const template = createStack({ importBucket: true });
      template.resourceCountIs("AWS::CloudFront::Distribution", 1);
    });

    it("still creates CloudFront function when importing bucket", () => {
      const template = createStack({ importBucket: true });
      template.resourceCountIs("AWS::CloudFront::Function", 1);
    });

    it("still creates ACM certificate when importing bucket", () => {
      const template = createStack({ importBucket: true });
      template.resourceCountIs("AWS::CertificateManager::Certificate", 1);
    });

    it("still creates Route53 record when importing bucket", () => {
      const template = createStack({ importBucket: true });
      template.hasResourceProperties("AWS::Route53::RecordSet", {
        Name: "test.example.com.",
        Type: "A",
      });
    });
  });
});
