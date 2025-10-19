"""Tests for orchestrator_lambda module."""
from __future__ import annotations
from src.ddb_workflow.orchestrator_lambda import (
    _invoke_worker,
    _pk,
    _sk_meta,
    _sk_task,
    handler,
)

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest

# Set environment variables before importing the module
os.environ.setdefault('TABLE_NAME', 'test-workflow-table')
os.environ.setdefault(
    'WORKER_ARN', 'arn:aws:lambda:us-east-1:123456789012:function:test-worker')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')


class TestOrchestratorLambdaHelpers:
    """Test helper functions in orchestrator lambda."""

    def test_pk_generation(self) -> None:
        """Test primary key generation."""
        workflow_id = "test-workflow-123"
        expected = "WORKFLOW#test-workflow-123"
        assert _pk(workflow_id) == expected

    def test_sk_meta_generation(self) -> None:
        """Test sort key generation for meta records."""
        expected = "META#WORKFLOW"
        assert _sk_meta() == expected

    def test_sk_task_generation(self) -> None:
        """Test sort key generation for task records."""
        task_id = "task-A"
        expected = "TASK#task-A"
        assert _sk_task(task_id) == expected

    @pytest.mark.parametrize("workflow_id,expected", [
        ("simple", "WORKFLOW#simple"),
        ("workflow-with-dashes", "WORKFLOW#workflow-with-dashes"),
        ("workflow_with_underscores", "WORKFLOW#workflow_with_underscores"),
        ("workflow123", "WORKFLOW#workflow123"),
        ("", "WORKFLOW#"),
    ])
    def test_pk_generation_various_inputs(self, workflow_id: str, expected: str) -> None:
        """Test PK generation with various workflow ID formats."""
        assert _pk(workflow_id) == expected

    @pytest.mark.parametrize("task_id,expected", [
        ("A", "TASK#A"),
        ("B1", "TASK#B1"),
        ("complex-task-name", "TASK#complex-task-name"),
        ("TASK_WITH_UNDERSCORES", "TASK#TASK_WITH_UNDERSCORES"),
        ("", "TASK#"),
    ])
    def test_sk_task_generation_various_inputs(self, task_id: str, expected: str) -> None:
        """Test SK task generation with various task ID formats."""
        assert _sk_task(task_id) == expected


class TestInvokeWorker:
    """Test the _invoke_worker function."""

    @patch('src.ddb_workflow.orchestrator_lambda.lambda_client')
    def test_invoke_worker_basic(self, mock_lambda_client: Mock) -> None:
        """Test basic worker invocation."""
        mock_lambda_client.invoke.return_value = {}

        task_request = {
            "workflowId": "test-workflow",
            "taskId": "test-task",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        _invoke_worker(task_request)

        # Verify lambda client was called correctly
        mock_lambda_client.invoke.assert_called_once()
        call_args = mock_lambda_client.invoke.call_args

        assert call_args[1]["FunctionName"] == os.environ["WORKER_ARN"]
        assert call_args[1]["InvocationType"] == "Event"

        # Verify payload
        payload = json.loads(call_args[1]["Payload"].decode("utf-8"))
        assert payload == task_request

    @patch('src.ddb_workflow.orchestrator_lambda.lambda_client')
    def test_invoke_worker_payload_serialization(self, mock_lambda_client: Mock) -> None:
        """Test that the payload is properly serialized."""
        mock_lambda_client.invoke.return_value = {}

        task_request = {
            "workflowId": "workflow-123",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 5,
            "deadlineMs": 30000,
            "correlationId": "correlation-456",
        }

        _invoke_worker(task_request)

        # Get the payload that was sent
        call_args = mock_lambda_client.invoke.call_args
        payload_bytes = call_args[1]["Payload"]
        payload_dict = json.loads(payload_bytes.decode("utf-8"))

        # Verify all fields are correctly serialized
        assert payload_dict["workflowId"] == "workflow-123"
        assert payload_dict["taskId"] == "A"
        assert payload_dict["targetLambdaArn"] == "arn:aws:lambda:us-east-1:123456789012:function:lambda-a"
        assert payload_dict["expectedVersion"] == 5
        assert payload_dict["deadlineMs"] == 30000
        assert payload_dict["correlationId"] == "correlation-456"

    @patch('src.ddb_workflow.orchestrator_lambda.lambda_client')
    def test_invoke_worker_lambda_error(self, mock_lambda_client: Mock) -> None:
        """Test worker invocation when Lambda invoke fails."""
        # Mock Lambda invoke to raise an exception
        mock_lambda_client.invoke.side_effect = Exception(
            "Lambda invoke failed")

        task_request = {
            "workflowId": "test-workflow",
            "taskId": "test-task",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        # Should raise the exception
        with pytest.raises(Exception, match="Lambda invoke failed"):
            _invoke_worker(task_request)


class TestOrchestratorHandler:
    """Test the main orchestrator handler function."""

    @patch('src.ddb_workflow.orchestrator_lambda._start_from_template')
    def test_handler_start_mode(self, mock_start_template: Mock, mock_lambda_context: Mock) -> None:
        """Test handler in start mode."""
        event = {
            "mode": "start",
            "workflowId": "test-workflow",
            "lambdas": {
                "A": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
                "B1": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
                "B2": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b2",
                "B3": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b3",
                "C": "arn:aws:lambda:us-east-1:123456789012:function:lambda-c",
            },
        }

        result = handler(event, mock_lambda_context)

        # Verify _start_from_template was called
        mock_start_template.assert_called_once_with(
            "test-workflow", event["lambdas"])

        # Verify return value
        assert result == {"ok": True, "workflowId": "test-workflow"}

    def test_handler_stream_mode(self, mock_lambda_context: Mock) -> None:
        """Test handler processing DynamoDB stream records."""
        event = {
            "Records": [
                {
                    "eventName": "MODIFY",
                    "dynamodb": {
                        "NewImage": {
                            "pk": {"S": "WORKFLOW#test"},
                            "sk": {"S": "TASK#A"},
                            "type": {"S": "TASK"},
                            "status": {"S": "SUCCEEDED"},
                            "taskId": {"S": "A"},
                            "dependents": {"S": "B1,B2,B3"},
                        },
                        "OldImage": {
                            "pk": {"S": "WORKFLOW#test"},
                            "sk": {"S": "TASK#A"},
                            "type": {"S": "TASK"},
                            "status": {"S": "RUNNING"},
                            "taskId": {"S": "A"},
                            "dependents": {"S": "B1,B2,B3"},
                        },
                    },
                },
            ],
        }

        with patch('src.ddb_workflow.orchestrator_lambda.ddb') as mock_ddb:
            # Mock successful dependency decrement
            mock_ddb.update_item.return_value = {
                "Attributes": {
                    "remainingDeps": {"N": "0"},
                    "targetLambdaArn": {"S": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1"},
                    "version": {"N": "0"},
                },
            }

            result = handler(event, mock_lambda_context)

        # Verify return value
        assert result == {"ok": True}

    def test_handler_invalid_mode(self, mock_lambda_context: Mock) -> None:
        """Test handler with invalid mode."""
        event = {
            "mode": "invalid_mode",
            "workflowId": "test-workflow",
        }

        result = handler(event, mock_lambda_context)

        # Should treat as stream mode and return ok
        assert result == {"ok": True}

    def test_handler_missing_mode_with_no_records(self, mock_lambda_context: Mock) -> None:
        """Test handler with missing mode and no records."""
        event = {
            "workflowId": "test-workflow",
        }

        result = handler(event, mock_lambda_context)

        # Should default to stream processing with no records
        assert result == {"ok": True}

    @patch('src.ddb_workflow.orchestrator_lambda._start_from_template')
    def test_handler_start_mode_missing_fields(self, mock_start_template: Mock, mock_lambda_context: Mock) -> None:
        """Test handler start mode with missing required fields."""
        event = {
            "mode": "start",
            # Missing workflowId and lambdas
        }

        # Should raise KeyError for missing fields
        with pytest.raises(KeyError):
            handler(event, mock_lambda_context)


class TestStartFromTemplate:
    """Test the _start_from_template function."""

    @patch('src.ddb_workflow.orchestrator_lambda._invoke_worker')
    @patch('src.ddb_workflow.orchestrator_lambda.table')
    def test_start_from_template_basic(self, mock_table: Mock, mock_invoke_worker: Mock) -> None:
        """Test basic workflow template seeding."""
        # Import the function to test
        from src.ddb_workflow.orchestrator_lambda import _start_from_template

        workflow_id = "test-workflow"
        lambdas = {
            "A": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "B1": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
            "B2": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b2",
            "B3": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b3",
            "C": "arn:aws:lambda:us-east-1:123456789012:function:lambda-c",
        }

        # Mock the batch_writer context manager
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer

        _start_from_template(workflow_id, lambdas)

        # Verify batch writer was used
        mock_table.batch_writer.assert_called_once()

        # Verify items were written (META + 5 tasks = 6 items)
        assert mock_batch_writer.put_item.call_count == 6

        # Verify worker was invoked for task A
        mock_invoke_worker.assert_called_once()
        call_args = mock_invoke_worker.call_args[0][0]
        assert call_args["taskId"] == "A"
        assert call_args["workflowId"] == workflow_id

    @patch('src.ddb_workflow.orchestrator_lambda._invoke_worker')
    @patch('src.ddb_workflow.orchestrator_lambda.table')
    def test_start_from_template_verify_items(self, mock_table: Mock, mock_invoke_worker: Mock) -> None:
        """Test that correct items are created in DynamoDB."""
        from src.ddb_workflow.orchestrator_lambda import _start_from_template

        workflow_id = "test-workflow"
        lambdas = {
            "A": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "B1": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
            "B2": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b2",
            "B3": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b3",
            "C": "arn:aws:lambda:us-east-1:123456789012:function:lambda-c",
        }

        # Mock the batch_writer context manager
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer

        _start_from_template(workflow_id, lambdas)

        # Get all the items that were put
        put_items = [call[1]["Item"]
                     for call in mock_batch_writer.put_item.call_args_list]

        # Verify META item
        meta_items = [item for item in put_items if item["type"] == "META"]
        assert len(meta_items) == 1
        meta_item = meta_items[0]
        assert meta_item["pk"] == f"WORKFLOW#{workflow_id}"
        assert meta_item["sk"] == "META#WORKFLOW"
        assert meta_item["status"] == "PENDING"

        # Verify TASK items
        task_items = [item for item in put_items if item["type"] == "TASK"]
        assert len(task_items) == 5

        # Verify task A (should be READY)
        task_a = next(item for item in task_items if item["taskId"] == "A")
        assert task_a["status"] == "READY"
        assert task_a["remainingDeps"] == 0
        assert task_a["dependsOn"] == ""

        # Verify task B1 (should be PENDING)
        task_b1 = next(item for item in task_items if item["taskId"] == "B1")
        assert task_b1["status"] == "PENDING"
        assert task_b1["remainingDeps"] == 1
        assert task_b1["dependsOn"] == "A"

        # Verify task C (should be PENDING)
        task_c = next(item for item in task_items if item["taskId"] == "C")
        assert task_c["status"] == "PENDING"
        assert task_c["remainingDeps"] == 3
        assert task_c["dependsOn"] == "B1,B2,B3"

    @patch('src.ddb_workflow.orchestrator_lambda._invoke_worker')
    @patch('src.ddb_workflow.orchestrator_lambda.table')
    def test_start_from_template_dependency_calculation(self, mock_table: Mock, mock_invoke_worker: Mock) -> None:
        """Test that dependencies are calculated correctly."""
        from src.ddb_workflow.orchestrator_lambda import _start_from_template

        workflow_id = "complex-workflow"
        lambdas = {
            "A": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "B1": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
            "B2": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b2",
            "B3": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b3",
            "C": "arn:aws:lambda:us-east-1:123456789012:function:lambda-c",
        }

        # Mock the batch_writer context manager
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch_writer

        _start_from_template(workflow_id, lambdas)

        # Get all task items
        put_items = [call[1]["Item"]
                     for call in mock_batch_writer.put_item.call_args_list]
        task_items = [item for item in put_items if item["type"] == "TASK"]

        # Verify dependency counts
        task_deps = {item["taskId"]: item["remainingDeps"]
                     for item in task_items}

        assert task_deps["A"] == 0  # No dependencies
        assert task_deps["B1"] == 1  # Depends on A
        assert task_deps["B2"] == 1  # Depends on A
        assert task_deps["B3"] == 1  # Depends on A
        assert task_deps["C"] == 3   # Depends on B1, B2, B3


@pytest.fixture
def mock_lambda_context() -> Mock:
    """Mock AWS Lambda context."""
    context = Mock()
    context.function_name = "test-orchestrator"
    context.request_id = "test-request-id"
    return context
