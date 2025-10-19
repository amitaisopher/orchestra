"""Tests for worker_lambda module."""
from __future__ import annotations

import json
import os
from unittest.mock import Mock, patch

import pytest

from src.ddb_workflow.worker_lambda import _pk, _sk_task, handler

# Set environment variables before importing the module
os.environ.setdefault('TABLE_NAME', 'test-workflow-table')
os.environ.setdefault(
    'WORKER_ARN', 'arn:aws:lambda:us-east-1:123456789012:function:test-worker')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')


class TestWorkerLambdaHelpers:
    """Test helper functions in worker lambda."""

    def test_pk_generation(self) -> None:
        """Test primary key generation."""
        workflow_id = "test-workflow-123"
        expected = "WORKFLOW#test-workflow-123"
        assert _pk(workflow_id) == expected

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


class TestWorkerHandler:
    """Test the worker lambda handler function."""

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_successful_execution(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test successful task execution."""
        # Mock DynamoDB update_item calls
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke
        mock_lambda_response = {
            "Payload": Mock(),
        }
        mock_lambda_response["Payload"].read.return_value = json.dumps(
            {"result": "success"}).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        result = handler(event, mock_lambda_context)

        # Verify result
        assert result["ok"] is True
        assert result["status"] == "SUCCEEDED"
        assert "durationMs" in result

        # Verify DynamoDB was called correctly
        assert mock_ddb.update_item.call_count == 2  # RUNNING update + SUCCEEDED update

        # Verify Lambda was invoked
        mock_lambda_client.invoke.assert_called_once()
        call_args = mock_lambda_client.invoke.call_args
        assert call_args[1]["FunctionName"] == event["targetLambdaArn"]
        assert call_args[1]["InvocationType"] == "RequestResponse"

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_conditional_check_failure(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test handler when conditional check fails (task not ready or version mismatch)."""
        # Import the exception class properly
        from botocore.exceptions import ClientError

        # Mock conditional check failure
        error_response = {'Error': {'Code': 'ConditionalCheckFailedException'}}
        mock_ddb.update_item.side_effect = ClientError(
            error_response, 'UpdateItem')

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        result = handler(event, mock_lambda_context)

        # Should return failure due to condition check
        assert result["ok"] is False
        assert result["reason"] == "Not READY or version mismatch"

        # Lambda should not be invoked
        mock_lambda_client.invoke.assert_not_called()

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_target_lambda_failure(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test handler when target lambda execution fails."""
        # Mock successful DynamoDB updates for first call (RUNNING state)
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke failure
        mock_lambda_client.invoke.side_effect = Exception(
            "Lambda execution failed")

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        result = handler(event, mock_lambda_context)

        # Should return failure
        assert result["ok"] is False
        assert result["status"] == "FAILED"
        assert "error" in result

        # Verify DynamoDB calls: RUNNING update + FAILED update
        assert mock_ddb.update_item.call_count == 2

        # Verify the FAILED update
        failed_call = mock_ddb.update_item.call_args_list[1]
        assert '"message": "Lambda execution failed"' in str(failed_call)

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_lambda_invoke_parameters(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test that Lambda is invoked with correct parameters."""
        # Mock DynamoDB update_item calls
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke
        mock_lambda_response = {
            "Payload": Mock(),
        }
        mock_lambda_response["Payload"].read.return_value = json.dumps(
            {"data": "test"}).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response

        event = {
            "workflowId": "workflow-123",
            "taskId": "B1",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
            "expectedVersion": 2,
            "deadlineMs": 30000,
            "correlationId": "correlation-456",
        }

        handler(event, mock_lambda_context)

        # Verify Lambda invoke parameters
        call_args = mock_lambda_client.invoke.call_args
        assert call_args[1]["FunctionName"] == event["targetLambdaArn"]
        assert call_args[1]["InvocationType"] == "RequestResponse"

        # Verify payload sent to target lambda
        payload = json.loads(call_args[1]["Payload"].decode("utf-8"))
        assert payload["workflowId"] == event["workflowId"]
        assert payload["taskId"] == event["taskId"]

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_dynamodb_updates(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test DynamoDB update operations in detail."""
        # Mock DynamoDB update_item calls
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke
        mock_lambda_response = {
            "Payload": Mock(),
        }
        mock_lambda_response["Payload"].read.return_value = json.dumps(
            {"result": "ok"}).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        handler(event, mock_lambda_context)

        # Verify DynamoDB update calls
        assert mock_ddb.update_item.call_count == 2

        # Check first call (RUNNING state)
        running_call = mock_ddb.update_item.call_args_list[0]
        running_args = running_call[1]

        assert running_args["TableName"] == "test-workflow-table"
        assert running_args["Key"]["pk"]["S"] == "WORKFLOW#test-workflow"
        assert running_args["Key"]["sk"]["S"] == "TASK#A"
        assert ":running" in str(running_args["ExpressionAttributeValues"])
        assert ":ready" in str(running_args["ExpressionAttributeValues"])
        assert ":ver" in str(running_args["ExpressionAttributeValues"])

        # Check second call (SUCCEEDED state)
        succeeded_call = mock_ddb.update_item.call_args_list[1]
        succeeded_args = succeeded_call[1]

        assert succeeded_args["TableName"] == "test-workflow-table"
        assert succeeded_args["Key"]["pk"]["S"] == "WORKFLOW#test-workflow"
        assert succeeded_args["Key"]["sk"]["S"] == "TASK#A"
        assert ":succeeded" in str(succeeded_args["ExpressionAttributeValues"])

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    @patch('src.ddb_workflow.worker_lambda.time')
    def test_handler_duration_calculation(
        self,
        mock_time: Mock,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test that execution duration is calculated correctly."""
        # Mock time.time() to return predictable values
        mock_time.time.side_effect = [1000.0, 1001.5]  # 1.5 seconds difference

        # Mock DynamoDB update_item calls
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke
        mock_lambda_response = {
            "Payload": Mock(),
        }
        mock_lambda_response["Payload"].read.return_value = json.dumps(
            {"result": "ok"}).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        result = handler(event, mock_lambda_context)

        # Verify duration calculation (1.5 seconds = 1500ms)
        assert result["durationMs"] == 1500

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_lambda_payload_processing(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test processing of Lambda response payload."""
        # Mock DynamoDB update_item calls
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke with complex response
        response_data = {
            "statusCode": 200,
            "body": {"message": "Task completed", "data": [1, 2, 3]},
            "headers": {"Content-Type": "application/json"},
        }
        mock_lambda_response = {
            "Payload": Mock(),
        }
        mock_lambda_response["Payload"].read.return_value = json.dumps(
            response_data).encode()
        mock_lambda_client.invoke.return_value = mock_lambda_response

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        handler(event, mock_lambda_context)

        # Verify the response was stored in DynamoDB
        succeeded_call = mock_ddb.update_item.call_args_list[1]
        succeeded_args = succeeded_call[1]

        # The result should be JSON-encoded in the DynamoDB update
        result_value = succeeded_args["ExpressionAttributeValues"][":res"]["S"]
        stored_result = json.loads(result_value)
        assert stored_result == response_data

    def test_handler_missing_required_fields(self, mock_lambda_context: Mock) -> None:
        """Test handler with missing required event fields."""
        incomplete_event = {
            "workflowId": "test-workflow",
            # Missing taskId, targetLambdaArn, etc.
        }

        with pytest.raises(KeyError):
            handler(incomplete_event, mock_lambda_context)

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_empty_lambda_response(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test handler when Lambda returns empty response."""
        # Mock DynamoDB update_item calls
        mock_ddb.update_item.return_value = {}

        # Mock Lambda invoke with no payload
        mock_lambda_response = {
            "Payload": None,
        }
        mock_lambda_client.invoke.return_value = mock_lambda_response

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 0,
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        result = handler(event, mock_lambda_context)

        # Should still succeed with empty result
        assert result["ok"] is True
        assert result["status"] == "SUCCEEDED"

    @patch('src.ddb_workflow.worker_lambda.lambda_client')
    @patch('src.ddb_workflow.worker_lambda.ddb')
    def test_handler_version_mismatch_scenario(
        self,
        mock_ddb: Mock,
        mock_lambda_client: Mock,
        mock_lambda_context: Mock,
    ) -> None:
        """Test the idempotency scenario with version mismatch."""
        from botocore.exceptions import ClientError

        # Mock conditional check failure due to version mismatch
        error_response = {'Error': {'Code': 'ConditionalCheckFailedException'}}
        mock_ddb.update_item.side_effect = ClientError(
            error_response, 'UpdateItem')

        event = {
            "workflowId": "test-workflow",
            "taskId": "A",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
            "expectedVersion": 5,  # Wrong version
            "deadlineMs": 15000,
            "correlationId": "test-correlation",
        }

        result = handler(event, mock_lambda_context)

        # Should gracefully handle version mismatch
        assert result["ok"] is False
        assert result["reason"] == "Not READY or version mismatch"

        # Only one DynamoDB call should be made (the failed conditional update)
        assert mock_ddb.update_item.call_count == 1

        # Lambda should not be invoked
        mock_lambda_client.invoke.assert_not_called()


@pytest.fixture
def mock_lambda_context() -> Mock:
    """Mock AWS Lambda context."""
    context = Mock()
    context.function_name = "test-worker"
    context.request_id = "test-request-id"
    return context
