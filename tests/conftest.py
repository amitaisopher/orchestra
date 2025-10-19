from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import boto3
import pytest


@pytest.fixture(autouse=True)
def mock_environment() -> Generator[None]:
    """Mock environment variables for all tests."""
    with patch.dict(os.environ, {
        'TABLE_NAME': 'test-workflow-table',
        'WORKER_ARN': 'arn:aws:lambda:us-east-1:123456789012:function:test-worker',
        'AWS_DEFAULT_REGION': 'us-east-1',
        'AWS_ACCESS_KEY_ID': 'testing',
        'AWS_SECRET_ACCESS_KEY': 'testing',
        'AWS_SECURITY_TOKEN': 'testing',
        'AWS_SESSION_TOKEN': 'testing',
    }):
        yield


@pytest.fixture
def mock_dynamodb_client() -> Any:
    """Mock DynamoDB client."""
    try:
        from moto import mock_dynamodb
        with mock_dynamodb():
            yield boto3.client('dynamodb', region_name='us-east-1')
    except ImportError:
        # If moto is not available, return a regular client
        yield boto3.client('dynamodb', region_name='us-east-1')


@pytest.fixture
def mock_dynamodb_resource() -> Any:
    """Mock DynamoDB resource."""
    try:
        from moto import mock_dynamodb
        with mock_dynamodb():
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

            # Create the workflow table
            dynamodb.create_table(
                TableName='test-workflow-table',
                KeySchema=[
                    {'AttributeName': 'pk', 'KeyType': 'HASH'},
                    {'AttributeName': 'sk', 'KeyType': 'RANGE'},
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'pk', 'AttributeType': 'S'},
                    {'AttributeName': 'sk', 'AttributeType': 'S'},
                ],
                BillingMode='PAY_PER_REQUEST',
                StreamSpecification={
                    'StreamEnabled': True,
                    'StreamViewType': 'NEW_AND_OLD_IMAGES',
                },
            )

            yield dynamodb
    except ImportError:
        # If moto is not available, return a regular resource
        yield boto3.resource('dynamodb', region_name='us-east-1')


@pytest.fixture
def mock_lambda_client() -> Any:
    """Mock Lambda client."""
    try:
        from moto import mock_lambda
        with mock_lambda():
            yield boto3.client('lambda', region_name='us-east-1')
    except ImportError:
        # If moto is not available, return a regular client
        yield boto3.client('lambda', region_name='us-east-1')


@pytest.fixture
def mock_stepfunctions_client() -> Any:
    """Mock Step Functions client."""
    try:
        from moto import mock_stepfunctions
        with mock_stepfunctions():
            yield boto3.client('stepfunctions', region_name='us-east-1')
    except ImportError:
        # If moto is not available, return a regular client
        yield boto3.client('stepfunctions', region_name='us-east-1')


@pytest.fixture
def sample_workflow_id() -> str:
    """Sample workflow ID for testing."""
    return "test-workflow-123"


@pytest.fixture
def sample_task_execution_request() -> dict[str, Any]:
    """Sample TaskExecutionRequest for testing."""
    return {
        "workflowId": "test-workflow-123",
        "taskId": "A",
        "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
        "expectedVersion": 0,
        "deadlineMs": 15000,
        "correlationId": "test-correlation-id",
    }


@pytest.fixture
def sample_lambdas_dict() -> dict[str, str]:
    """Sample lambda ARNs dictionary for testing."""
    return {
        "A": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
        "B1": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
        "B2": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b2",
        "B3": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b3",
        "C": "arn:aws:lambda:us-east-1:123456789012:function:lambda-c",
    }


@pytest.fixture
def mock_lambda_context() -> MagicMock:
    """Mock AWS Lambda context object."""
    context = MagicMock()
    context.function_name = "test-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    context.memory_limit_in_mb = "128"
    context.remaining_time_in_millis = lambda: 30000
    context.request_id = "test-request-id"
    context.log_group_name = "/aws/lambda/test-function"
    context.log_stream_name = "2023/10/19/[$LATEST]test-stream"
    return context
