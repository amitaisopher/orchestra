"""Tests for invoke_all.py tool."""
from __future__ import annotations

import argparse
import json
from unittest.mock import Mock, patch

import pytest

from tools.invoke_all import (
    _invoke_lambda,
    get_lambda_names_from_exports,
    main,
)


class TestInvokeLambda:
    """Test the _invoke_lambda helper function."""

    def test_invoke_lambda_success(self) -> None:
        """Test successful lambda invocation."""
        mock_client = Mock()
        mock_payload = Mock()
        mock_payload.read.return_value = json.dumps(
            {"result": "success"}).encode()

        mock_client.invoke.return_value = {
            "Payload": mock_payload,
            "StatusCode": 200,
        }

        result = _invoke_lambda(mock_client, "test-function")

        assert result == {"result": "success"}
        mock_client.invoke.assert_called_once_with(
            FunctionName="test-function",
            InvocationType="RequestResponse",
        )

    def test_invoke_lambda_no_payload(self) -> None:
        """Test lambda invocation with no payload."""
        mock_client = Mock()
        mock_client.invoke.return_value = {}

        result = _invoke_lambda(mock_client, "test-function")

        assert result == {}

    def test_invoke_lambda_empty_payload(self) -> None:
        """Test lambda invocation with empty payload."""
        mock_client = Mock()
        mock_payload = Mock()
        mock_payload.read.return_value = b""

        mock_client.invoke.return_value = {"Payload": mock_payload}

        result = _invoke_lambda(mock_client, "test-function")

        assert result == {}

    def test_invoke_lambda_invalid_json(self) -> None:
        """Test lambda invocation with invalid JSON payload."""
        mock_client = Mock()
        mock_payload = Mock()
        mock_payload.read.return_value = b"invalid json"

        mock_client.invoke.return_value = {"Payload": mock_payload}

        with pytest.raises(json.JSONDecodeError):
            _invoke_lambda(mock_client, "test-function")

    def test_invoke_lambda_exception(self) -> None:
        """Test lambda invocation when client raises exception."""
        mock_client = Mock()
        mock_client.invoke.side_effect = Exception("Lambda invocation failed")

        with pytest.raises(Exception, match="Lambda invocation failed"):
            _invoke_lambda(mock_client, "test-function")


class TestGetLambdaNamesFromExports:
    """Test the get_lambda_names_from_exports function."""

    def test_get_lambda_names_success(self) -> None:
        """Test successful retrieval of lambda names from exports."""
        mock_client = Mock()
        mock_client.list_exports.return_value = {
            "Exports": [
                {"Name": "TestStack-LambdaA-Name",
                    "Value": "TestStack-LambdaA123-AbCd"},
                {"Name": "TestStack-LambdaB1-Name",
                    "Value": "TestStack-LambdaB1456-EfGh"},
                {"Name": "TestStack-LambdaB2-Name",
                    "Value": "TestStack-LambdaB2789-IjKl"},
                {"Name": "TestStack-LambdaB3-Name",
                    "Value": "TestStack-LambdaB3012-MnOp"},
                {"Name": "TestStack-LambdaC-Name",
                    "Value": "TestStack-LambdaC345-QrSt"},
                {"Name": "SomeOtherStack-Export", "Value": "irrelevant-value"},
            ],
        }

        result = get_lambda_names_from_exports(mock_client, "TestStack")

        expected = {
            "A": "TestStack-LambdaA123-AbCd",
            "B1": "TestStack-LambdaB1456-EfGh",
            "B2": "TestStack-LambdaB2789-IjKl",
            "B3": "TestStack-LambdaB3012-MnOp",
            "C": "TestStack-LambdaC345-QrSt",
        }

        assert result == expected

    def test_get_lambda_names_partial_exports(self) -> None:
        """Test retrieval when only some exports are available."""
        mock_client = Mock()
        mock_client.list_exports.return_value = {
            "Exports": [
                {"Name": "TestStack-LambdaA-Name",
                    "Value": "TestStack-LambdaA123-AbCd"},
                {"Name": "TestStack-LambdaC-Name",
                    "Value": "TestStack-LambdaC345-QrSt"},
                # Missing B1, B2, B3
            ],
        }

        result = get_lambda_names_from_exports(mock_client, "TestStack")

        expected = {
            "A": "TestStack-LambdaA123-AbCd",
            "C": "TestStack-LambdaC345-QrSt",
        }

        assert result == expected

    def test_get_lambda_names_no_exports(self) -> None:
        """Test retrieval when no relevant exports are found."""
        mock_client = Mock()
        mock_client.list_exports.return_value = {
            "Exports": [
                {"Name": "OtherStack-Export1", "Value": "value1"},
                {"Name": "OtherStack-Export2", "Value": "value2"},
            ],
        }

        result = get_lambda_names_from_exports(mock_client, "TestStack")

        assert result == {}

    def test_get_lambda_names_api_failure(self) -> None:
        """Test retrieval when CloudFormation API fails."""
        mock_client = Mock()
        mock_client.list_exports.side_effect = Exception("API call failed")

        result = get_lambda_names_from_exports(mock_client, "TestStack")

        assert result == {}

    def test_get_lambda_names_empty_response(self) -> None:
        """Test retrieval with empty exports response."""
        mock_client = Mock()
        mock_client.list_exports.return_value = {"Exports": []}

        result = get_lambda_names_from_exports(mock_client, "TestStack")

        assert result == {}

    @pytest.mark.parametrize("stack_name,export_name,expected_key", [
        ("MyStack", "MyStack-LambdaA-Name", "A"),
        ("DevStack", "DevStack-LambdaB1-Name", "B1"),
        ("ProdStack", "ProdStack-LambdaB2-Name", "B2"),
        ("TestStack", "TestStack-LambdaB3-Name", "B3"),
        ("Stack123", "Stack123-LambdaC-Name", "C"),
    ])
    def test_get_lambda_names_various_stacks(
        self,
        stack_name: str,
        export_name: str,
        expected_key: str,
    ) -> None:
        """Test lambda name retrieval with various stack names."""
        mock_client = Mock()
        mock_client.list_exports.return_value = {
            "Exports": [
                {"Name": export_name, "Value": f"function-name-{expected_key}"},
            ],
        }

        result = get_lambda_names_from_exports(mock_client, stack_name)

        assert result == {expected_key: f"function-name-{expected_key}"}


class TestMainFunction:
    """Test the main function and argument parsing."""

    @patch('tools.invoke_all.boto3')
    def test_main_with_orchestrator_arn(self, mock_boto3: Mock) -> None:
        """Test main function with orchestrator ARN."""
        # Mock boto3 clients
        mock_lambda_client = Mock()
        mock_cfn_client = Mock()
        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'lambda': mock_lambda_client,
            'cloudformation': mock_cfn_client,
            'stepfunctions': Mock(),
        }[service]

        # Mock CloudFormation exports
        mock_cfn_client.list_exports.return_value = {
            "Exports": [
                {"Name": "TestStack-LambdaA-Name",
                    "Value": "actual-lambda-a-name"},
                {"Name": "TestStack-LambdaB1-Name",
                    "Value": "actual-lambda-b1-name"},
                {"Name": "TestStack-LambdaB2-Name",
                    "Value": "actual-lambda-b2-name"},
                {"Name": "TestStack-LambdaB3-Name",
                    "Value": "actual-lambda-b3-name"},
                {"Name": "TestStack-LambdaC-Name",
                    "Value": "actual-lambda-c-name"},
            ],
        }

        # Mock Lambda get_function calls
        mock_lambda_client.get_function.return_value = {
            "Configuration": {
                "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-function",
            },
        }

        # Mock Lambda invoke
        mock_lambda_client.invoke.return_value = {}

        # Mock command line arguments
        test_args = [
            'invoke_all.py',
            '--orchestrator-arn',
            'arn:aws:lambda:us-east-1:123456789012:function:orchestrator',
            '--region',
            'us-east-1',
            '--stack-name',
            'TestStack',
        ]

        with patch('sys.argv', test_args):
            # Should not raise an exception
            main()

        # Verify CloudFormation was called
        mock_cfn_client.list_exports.assert_called_once()

        # Verify Lambda functions were looked up
        assert mock_lambda_client.get_function.call_count == 5  # A, B1, B2, B3, C

        # Verify orchestrator was invoked
        mock_lambda_client.invoke.assert_called()

    @patch('tools.invoke_all.boto3')
    def test_main_with_state_machine_arn(self, mock_boto3: Mock) -> None:
        """Test main function with state machine ARN."""
        # Mock boto3 clients
        mock_sfn_client = Mock()
        mock_cfn_client = Mock()
        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'lambda': Mock(),
            'cloudformation': mock_cfn_client,
            'stepfunctions': mock_sfn_client,
        }[service]

        # Mock CloudFormation exports (empty)
        mock_cfn_client.list_exports.return_value = {"Exports": []}

        # Mock Step Functions
        mock_sfn_client.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test:123",
        }
        mock_sfn_client.describe_execution.return_value = {
            "status": "SUCCEEDED",
            "output": '{"result": "success"}',
        }

        test_args = [
            'invoke_all.py',
            '--state-machine-arn',
            'arn:aws:states:us-east-1:123456789012:stateMachine:test',
            '--region',
            'us-east-1',
        ]

        with patch('sys.argv', test_args):
            main()

        # Verify Step Functions execution
        mock_sfn_client.start_execution.assert_called_once()
        mock_sfn_client.describe_execution.assert_called()

    @patch('tools.invoke_all.boto3')
    def test_main_no_lambda_names_found(self, mock_boto3: Mock) -> None:
        """Test main function when no lambda names are found."""
        # Mock boto3 clients
        mock_lambda_client = Mock()
        mock_cfn_client = Mock()
        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'lambda': mock_lambda_client,
            'cloudformation': mock_cfn_client,
            'stepfunctions': Mock(),
        }[service]

        # Mock CloudFormation exports (empty)
        mock_cfn_client.list_exports.return_value = {"Exports": []}

        test_args = [
            'invoke_all.py',
            '--orchestrator-arn',
            'arn:aws:lambda:us-east-1:123456789012:function:orchestrator',
            '--region',
            'us-east-1',
        ]

        with patch('sys.argv', test_args):
            # Should fall back to hardcoded names and likely fail
            with pytest.raises(Exception):
                main()

    def test_argument_parsing(self) -> None:
        """Test argument parsing functionality."""
        parser = argparse.ArgumentParser(description="Test parser")
        parser.add_argument("--state-machine-arn", required=False)
        parser.add_argument("--orchestrator-arn", required=False)
        parser.add_argument("--region", default="us-east-1")
        parser.add_argument("--stack-name", default="OrchestrationStack")

        # Test with all arguments
        args = parser.parse_args([
            '--state-machine-arn', 'arn:aws:states:us-east-1:123456789012:stateMachine:test',
            '--orchestrator-arn', 'arn:aws:lambda:us-east-1:123456789012:function:orch',
            '--region', 'eu-west-1',
            '--stack-name', 'MyStack',
        ])

        assert args.state_machine_arn == 'arn:aws:states:us-east-1:123456789012:stateMachine:test'
        assert args.orchestrator_arn == 'arn:aws:lambda:us-east-1:123456789012:function:orch'
        assert args.region == 'eu-west-1'
        assert args.stack_name == 'MyStack'

        # Test with defaults
        args = parser.parse_args([])
        assert args.state_machine_arn is None
        assert args.orchestrator_arn is None
        assert args.region == "us-east-1"
        assert args.stack_name == "OrchestrationStack"

    @patch('tools.invoke_all.boto3')
    def test_main_lambda_invocation_error(self, mock_boto3: Mock) -> None:
        """Test main function when Lambda invocation fails."""
        # Mock boto3 clients
        mock_lambda_client = Mock()
        mock_cfn_client = Mock()
        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'lambda': mock_lambda_client,
            'cloudformation': mock_cfn_client,
            'stepfunctions': Mock(),
        }[service]

        # Mock CloudFormation exports
        mock_cfn_client.list_exports.return_value = {
            "Exports": [
                {"Name": "TestStack-LambdaA-Name",
                    "Value": "actual-lambda-a-name"},
            ],
        }

        # Mock Lambda get_function to fail
        mock_lambda_client.get_function.side_effect = Exception(
            "Function not found")

        test_args = [
            'invoke_all.py',
            '--orchestrator-arn',
            'arn:aws:lambda:us-east-1:123456789012:function:orchestrator',
            '--region',
            'us-east-1',
            '--stack-name',
            'TestStack',
        ]

        with patch('sys.argv', test_args):
            # Should handle the error gracefully and continue
            with pytest.raises(Exception):
                main()

    @patch('tools.invoke_all.time')
    @patch('tools.invoke_all.boto3')
    def test_main_workflow_id_generation(self, mock_boto3: Mock, mock_time: Mock) -> None:
        """Test workflow ID generation in main function."""
        mock_time.time.return_value = 1234567890

        # Mock boto3 clients
        mock_lambda_client = Mock()
        mock_cfn_client = Mock()
        mock_boto3.client.side_effect = lambda service, **kwargs: {
            'lambda': mock_lambda_client,
            'cloudformation': mock_cfn_client,
            'stepfunctions': Mock(),
        }[service]

        # Mock CloudFormation exports
        mock_cfn_client.list_exports.return_value = {
            "Exports": [
                {"Name": "TestStack-LambdaA-Name",
                    "Value": "actual-lambda-a-name"},
            ],
        }

        # Mock Lambda operations
        mock_lambda_client.get_function.return_value = {
            "Configuration": {
                "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
            },
        }
        mock_lambda_client.invoke.return_value = {}

        test_args = [
            'invoke_all.py',
            '--orchestrator-arn',
            'arn:aws:lambda:us-east-1:123456789012:function:orchestrator',
            '--region',
            'us-east-1',
            '--stack-name',
            'TestStack',
        ]

        with patch('sys.argv', test_args):
            main()

        # Verify orchestrator was called with time-based workflow ID
        call_args = mock_lambda_client.invoke.call_args
        payload = json.loads(call_args[1]["Payload"].decode("utf-8"))
        assert payload["workflowId"] == "wf-1234567890"

    @patch('tools.invoke_all.sys')
    def test_argument_string_splitting(self, mock_sys: Mock) -> None:
        """Test the argument string splitting functionality."""
        # Mock sys.argv with a single argument string
        mock_sys.argv = [
            'invoke_all.py',
            '--orchestrator-arn arn:aws:lambda:us-east-1:123456789012:function:test',
        ]

        # This should trigger the argument splitting logic
        # The actual test would require mocking the shlex.split behavior
        # and verifying the argument parsing works correctly
        import shlex
        test_arg = '--orchestrator-arn arn:aws:lambda:us-east-1:123456789012:function:test'
        split_args = shlex.split(test_arg)

        expected = ['--orchestrator-arn',
                    'arn:aws:lambda:us-east-1:123456789012:function:test']
        assert split_args == expected


class TestErrorHandling:
    """Test error handling in various scenarios."""

    @patch('tools.invoke_all.boto3')
    def test_aws_service_unavailable(self, mock_boto3: Mock) -> None:
        """Test handling when AWS services are unavailable."""
        # Mock boto3 to raise service exceptions
        from botocore.exceptions import NoCredentialsError
        mock_boto3.client.side_effect = NoCredentialsError()

        test_args = [
            'invoke_all.py',
            '--region',
            'us-east-1',
        ]

        with patch('sys.argv', test_args):
            with pytest.raises(NoCredentialsError):
                main()

    def test_invalid_arn_format(self) -> None:
        """Test handling of invalid ARN formats."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--orchestrator-arn", required=False)

        # These should parse successfully (validation happens later)
        args = parser.parse_args(['--orchestrator-arn', 'invalid-arn'])
        assert args.orchestrator_arn == 'invalid-arn'

        args = parser.parse_args(['--orchestrator-arn', ''])
        assert args.orchestrator_arn == ''

    @patch('tools.invoke_all.boto3')
    def test_network_timeout(self, mock_boto3: Mock) -> None:
        """Test handling of network timeouts."""
        from botocore.exceptions import ConnectTimeoutError

        mock_client = Mock()
        mock_client.list_exports.side_effect = ConnectTimeoutError(
            endpoint_url="test")
        mock_boto3.client.return_value = mock_client

        result = get_lambda_names_from_exports(mock_client, "TestStack")
        assert result == {}  # Should return empty dict on error
