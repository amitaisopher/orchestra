from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class WorkflowManagementStack(Stack):
    """REST API (API Gateway + Lambda proxy) and static dashboard (S3 site)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        workflow_state_table: dynamodb.ITable,
        orchestrator_fn: _lambda.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ROOT = Path(__file__).resolve().parents[2]      # repo root
        CODE_ROOT = str(ROOT / "src")                   # contains api/

        logs_policy = iam.ManagedPolicy(
            self,
            "MgmtApiBasicLogs",
            statements=[
                iam.PolicyStatement(
                    actions=["logs:CreateLogGroup",
                             "logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=["xray:PutTraceSegments",
                             "xray:PutTelemetryRecords"],
                    resources=["*"],
                ),
            ],
        )

        # API Lambda
        api_log_group = logs.LogGroup(self, "WorkflowsApiLogGroup",
                                      retention=logs.RetentionDays.THREE_MONTHS)
        workflows_api = _lambda.Function(
            self,
            "WorkflowsApiLambda",
            code=_lambda.Code.from_asset(CODE_ROOT),
            handler="api.workflows_api.handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=api_log_group,
            tracing=_lambda.Tracing.ACTIVE,
            environment={
                # type: ignore[attr-defined]
                "TABLE_NAME": workflow_state_table.table_name,
                "ORCHESTRATOR_ARN": orchestrator_fn.function_arn,
            },
        )
        if workflows_api.role:
            workflows_api.role.add_managed_policy(logs_policy)

        workflow_state_table.grant_read_write_data(workflows_api)
        orchestrator_fn.grant_invoke(workflows_api)

        # API Gateway (proxy integration with automatic CORS)
        api = apigw.LambdaRestApi(
            self,
            "WorkflowsApi",
            handler=workflows_api,
            proxy=True,
            rest_api_name="workflows-api",
            deploy_options=apigw.StageOptions(
                metrics_enabled=True, tracing_enabled=True),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type",
                               "X-Requested-With", "Authorization"],
            ),
        )

        # Static website bucket (deploy Vite build from web/workflow-dashboard/dist)
        site_bucket = s3.Bucket(
            self,
            "WorkflowDashboardBucket",
            website_index_document="index.html",
            public_read_access=True,  # demo only; prefer CloudFront in prod
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                ignore_public_acls=False,
                block_public_policy=False,
                restrict_public_buckets=False,
            ),
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        s3deploy.BucketDeployment(
            self,
            "WorkflowDashboardDeploy",
            sources=[s3deploy.Source.asset("web/workflow-dashboard/dist")],
            destination_bucket=site_bucket,
        )

        # Outputs for easy access
        from aws_cdk import CfnOutput
        CfnOutput(
            self,
            "DashboardUrl",
            value=site_bucket.bucket_website_url,
            description="Workflow Dashboard URL",
        )
