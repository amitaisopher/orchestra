from __future__ import annotations

from pathlib import Path

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class FrontendStack(Stack):
    """Frontend static website deployment with automatic build."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ROOT = Path(__file__).resolve().parents[2]      # repo root
        FRONTEND_ROOT = ROOT / "web" / "workflow-dashboard"

        # Static website bucket
        site_bucket = s3.Bucket(
            self,
            "WorkflowDashboardBucket",
            website_index_document="index.html",
            public_read_access=True,  # For demo purposes
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                ignore_public_acls=False,
                block_public_policy=False,
                restrict_public_buckets=False,
            ),
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Deploy the built frontend with runtime configuration replacement
        s3deploy.BucketDeployment(
            self,
            "WorkflowDashboardDeploy",
            sources=[
                s3deploy.Source.asset(str(FRONTEND_ROOT / "dist")),
                # Replace the placeholder config.js with the real API URL
                s3deploy.Source.data(
                    "config.js",
                    f"window.API_BASE = '{api_url.rstrip('/')}';",
                ),
            ],
            destination_bucket=site_bucket,
        )

        # Store the website URL
        self.website_url = site_bucket.bucket_website_url

        # Outputs for easy access
        from aws_cdk import CfnOutput
        CfnOutput(
            self,
            "DashboardUrl",
            value=self.website_url,
            description="Workflow Dashboard URL",
        )
