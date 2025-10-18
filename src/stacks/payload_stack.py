from __future__ import annotations

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class PayloadStack(Stack):
    """Ingress and payload plumbing resources.

    Contains:
      * DynamoDB table with streams for the DDB-driven orchestrator
      * ECR repository (optional) for the container Lambda (B3)
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.workflow_state_table: dynamodb.Table = dynamodb.Table(
            self,
            "WorkflowStateTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            table_name="WorkflowStateTable",
            removal_policy=None,  # keep default (RETAIN) for safety; adjust for dev if needed
        )

        self.b3_ecr_repo: ecr.Repository = ecr.Repository(
            self,
            "B3EcrRepo",
            repository_name="lambda-b3-container",
            image_scan_on_push=True,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=10)],
            empty_on_delete=False,
            removal_policy=RemovalPolicy.DESTROY,  # keep default (RETAIN) for safety; adjust for dev if needed
        )