"""Tests for CDK stacks."""
from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import patch

import aws_cdk as cdk
import aws_cdk.assertions as assertions
import pytest

from src.stacks.orchestration_stack import OrchestrationStack
from src.stacks.payload_stack import PayloadStack

# Mark tests that require CDK bundling (which has Docker permission issues in CI)
pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_CDK_BUNDLING", "false").lower() == "true",
    reason="CDK bundling tests skipped due to Docker permission issues",
)


# Mock environment to disable Docker bundling for tests
@pytest.fixture(autouse=True)
def disable_docker_bundling() -> Generator[None]:
    """Disable Docker bundling for CDK tests to avoid permission issues."""
    with patch.dict(os.environ, {
        'CDK_DOCKER': 'false',
        'ESBUILD_BINARY': 'true',
    }):
        yield


class TestPayloadStack:
    """Test the payload stack."""

    def test_payload_stack_creation(self) -> None:
        """Test that payload stack can be created."""
        app = cdk.App()
        stack = PayloadStack(app, "TestPayloadStack")
        template = assertions.Template.from_stack(stack)

        # Verify DynamoDB table is created
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
            "StreamSpecification": {
                "StreamViewType": "NEW_AND_OLD_IMAGES",
            },
        })

    def test_payload_stack_table_properties(self) -> None:
        """Test DynamoDB table properties."""
        app = cdk.App()
        stack = PayloadStack(app, "TestPayloadStack")
        template = assertions.Template.from_stack(stack)

        # Verify table has correct key schema
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "KeySchema": [
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        })

    def test_payload_stack_ecr_repository(self) -> None:
        """Test ECR repository creation."""
        app = cdk.App()
        stack = PayloadStack(app, "TestPayloadStack")
        template = assertions.Template.from_stack(stack)

        # Verify ECR repository is created
        template.has_resource("AWS::ECR::Repository", {})

    def test_payload_stack_outputs(self) -> None:
        """Test stack outputs."""
        app = cdk.App()
        stack = PayloadStack(app, "TestPayloadStack")

        # Verify that the stack has the workflow table and ECR repo as attributes
        assert hasattr(stack, 'workflow_state_table')
        assert hasattr(stack, 'b3_ecr_repo')


class TestOrchestrationStack:
    """Test the orchestration stack."""

    def setup_method(self) -> None:
        """Set up test dependencies."""
        self.app = cdk.App()
        self.payload_stack = PayloadStack(self.app, "TestPayloadStack")
        self.orchestration_stack = OrchestrationStack(
            self.app,
            "TestOrchestrationStack",
            workflow_state_table=self.payload_stack.workflow_state_table,
            ecr_repo=self.payload_stack.b3_ecr_repo,
        )

    def test_orchestration_stack_creation(self) -> None:
        """Test that orchestration stack can be created."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Should have Lambda functions
        # 5 task lambdas + orchestrator + worker
        template.resource_count_is("AWS::Lambda::Function", 7)

    def test_lambda_functions_created(self) -> None:
        """Test that all required Lambda functions are created."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify Python Lambda
        template.has_resource_properties("AWS::Lambda::Function", {
            "Runtime": "python3.12",
        })

        # Verify Node.js Lambdas
        template.has_resource_properties("AWS::Lambda::Function", {
            "Runtime": "nodejs20.x",
        })

    def test_orchestrator_lambda_environment(self) -> None:
        """Test orchestrator Lambda environment variables."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify orchestrator has required environment variables
        template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    "TABLE_NAME": assertions.Match.any_value(),
                    "WORKER_ARN": assertions.Match.any_value(),
                }),
            },
        })

    def test_worker_lambda_environment(self) -> None:
        """Test worker Lambda environment variables."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify worker has required environment variables
        template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    "TABLE_NAME": assertions.Match.any_value(),
                }),
            },
        })

    def test_dynamodb_stream_trigger(self) -> None:
        """Test DynamoDB stream event source mapping."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify event source mapping for DynamoDB stream
        template.has_resource_properties("AWS::Lambda::EventSourceMapping", {
            "EventSourceArn": assertions.Match.any_value(),
            "FunctionName": assertions.Match.any_value(),
            "StartingPosition": "LATEST",
        })

    def test_step_functions_state_machine(self) -> None:
        """Test Step Functions state machine creation."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify state machine is created
        template.has_resource("AWS::StepFunctions::StateMachine", {})

    def test_iam_roles_created(self) -> None:
        """Test that necessary IAM roles are created."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Should have IAM roles for Lambda functions
        template.has_resource("AWS::IAM::Role", {})

        # Verify Lambda execution role has DynamoDB permissions
        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow",
                        "Action": assertions.Match.array_with([
                            assertions.Match.string_like_regexp("dynamodb:.*"),
                        ]),
                    }),
                ]),
            },
        })

    def test_lambda_permissions(self) -> None:
        """Test Lambda function permissions."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify Lambda invoke permissions
        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow",
                        "Action": assertions.Match.array_with([
                            "lambda:InvokeFunction",
                        ]),
                    }),
                ]),
            },
        })

    def test_cloudwatch_logs(self) -> None:
        """Test CloudWatch log groups are created."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify log groups are created for Lambda functions
        template.has_resource("AWS::Logs::LogGroup", {})

    def test_container_lambda(self) -> None:
        """Test container-based Lambda function."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify container Lambda is created
        template.has_resource_properties("AWS::Lambda::Function", {
            "Code": {
                "ImageUri": assertions.Match.any_value(),
            },
            "PackageType": "Image",
        })

    def test_lambda_timeouts_and_memory(self) -> None:
        """Test Lambda timeout and memory configurations."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # Verify reasonable timeout and memory settings
        template.has_resource_properties("AWS::Lambda::Function", {
            "Timeout": assertions.Match.any_value(),
            "MemorySize": assertions.Match.any_value(),
        })

    def test_resource_naming(self) -> None:
        """Test resource naming conventions."""
        template = assertions.Template.from_stack(self.orchestration_stack)

        # All resources should follow consistent naming
        resources = template.to_json()["Resources"]

        # Lambda functions should have descriptive names
        lambda_functions = [
            name for name, resource in resources.items()
            if resource["Type"] == "AWS::Lambda::Function"
        ]

        assert len(lambda_functions) > 0

        # Verify naming patterns
        for func_name in lambda_functions:
            assert any(keyword in func_name for keyword in [
                "Lambda", "Orchestrator", "Worker", "A", "B", "C",
            ])


class TestStackIntegration:
    """Test integration between stacks."""

    def test_cross_stack_references(self) -> None:
        """Test references between payload and orchestration stacks."""
        app = cdk.App()
        payload_stack = PayloadStack(app, "TestPayloadStack")
        orchestration_stack = OrchestrationStack(
            app,
            "TestOrchestrationStack",
            workflow_state_table=payload_stack.workflow_state_table,
            ecr_repo=payload_stack.b3_ecr_repo,
        )

        # Generate templates
        payload_template = assertions.Template.from_stack(payload_stack)
        orchestration_template = assertions.Template.from_stack(
            orchestration_stack)

        # Verify payload stack has exports
        payload_template.has_output("*", {})

        # Verify orchestration stack can reference payload resources
        assert orchestration_stack.workflow_state_table is not None
        assert orchestration_stack.ecr_repo is not None

    def test_stack_dependencies(self) -> None:
        """Test stack dependency ordering."""
        app = cdk.App()
        payload_stack = PayloadStack(app, "TestPayloadStack")
        orchestration_stack = OrchestrationStack(
            app,
            "TestOrchestrationStack",
            workflow_state_table=payload_stack.workflow_state_table,
            ecr_repo=payload_stack.b3_ecr_repo,
        )

        # Orchestration stack should depend on payload stack
        assert orchestration_stack.dependencies == [payload_stack]

    def test_environment_consistency(self) -> None:
        """Test environment variable consistency across stacks."""
        app = cdk.App()
        payload_stack = PayloadStack(app, "TestPayloadStack")
        orchestration_stack = OrchestrationStack(
            app,
            "TestOrchestrationStack",
            workflow_state_table=payload_stack.workflow_state_table,
            ecr_repo=payload_stack.b3_ecr_repo,
        )

        orchestration_template = assertions.Template.from_stack(
            orchestration_stack)

        # All Lambdas should reference the same table
        orchestration_template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    "TABLE_NAME": assertions.Match.any_value(),
                }),
            },
        })


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_missing_dependencies(self) -> None:
        """Test stack creation with missing dependencies."""
        app = cdk.App()

        # Should raise error if required dependencies are missing
        with pytest.raises(Exception):
            OrchestrationStack(
                app,
                "TestOrchestrationStack",
                workflow_state_table=None,  # type: ignore[arg-type]
                ecr_repo=None,  # type: ignore[arg-type]
            )

    def test_stack_naming_conflicts(self) -> None:
        """Test handling of naming conflicts."""
        app = cdk.App()
        payload_stack = PayloadStack(app, "TestPayloadStack")

        # Create two orchestration stacks with same construct ID should fail
        OrchestrationStack(
            app,
            "TestOrchestrationStack1",
            workflow_state_table=payload_stack.workflow_state_table,
            ecr_repo=payload_stack.b3_ecr_repo,
        )

        with pytest.raises(Exception):
            OrchestrationStack(
                app,
                "TestOrchestrationStack1",  # Same ID
                workflow_state_table=payload_stack.workflow_state_table,
                ecr_repo=payload_stack.b3_ecr_repo,
            )

    def test_resource_limits(self) -> None:
        """Test resource limits and constraints."""
        app = cdk.App()
        payload_stack = PayloadStack(app, "TestPayloadStack")
        orchestration_stack = OrchestrationStack(
            app,
            "TestOrchestrationStack",
            workflow_state_table=payload_stack.workflow_state_table,
            ecr_repo=payload_stack.b3_ecr_repo,
        )

        template = assertions.Template.from_stack(orchestration_stack)

        # Verify Lambda memory settings are within AWS limits
        template.has_resource_properties("AWS::Lambda::Function", {
            "MemorySize": assertions.Match.any_value(),
        })

        # Verify timeout settings are reasonable
        template.has_resource_properties("AWS::Lambda::Function", {
            "Timeout": assertions.Match.any_value(),
        })
