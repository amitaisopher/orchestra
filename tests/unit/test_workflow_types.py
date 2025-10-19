"""Tests for workflow_types module."""
from __future__ import annotations

import pytest

from src.ddb_workflow.workflow_types import (
    StartWorkflowRequest,
    Status,
    TaskDefinition,
    TaskExecutionRequest,
)


class TestWorkflowTypes:
    """Test workflow type definitions."""

    def test_status_literals(self) -> None:
        """Test that Status accepts only valid literal values."""
        valid_statuses: list[Status] = [
            "PENDING",
            "READY",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "CANCELED",
        ]

        for status in valid_statuses:
            # These should not raise type errors
            assert isinstance(status, str)
            assert status in ["PENDING", "READY", "RUNNING",
                              "SUCCEEDED", "FAILED", "CANCELED"]

    def test_task_definition_structure(self) -> None:
        """Test TaskDefinition TypedDict structure."""
        task_def: TaskDefinition = {
            "taskId": "test-task",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
            "dependsOn": ["task-a", "task-b"],
        }

        assert task_def["taskId"] == "test-task"
        assert task_def["targetLambdaArn"] == "arn:aws:lambda:us-east-1:123456789012:function:test"
        assert task_def["dependsOn"] == ["task-a", "task-b"]

        # Test with empty dependencies
        task_def_empty: TaskDefinition = {
            "taskId": "root-task",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:root",
            "dependsOn": [],
        }

        assert task_def_empty["dependsOn"] == []

    def test_task_execution_request_structure(self) -> None:
        """Test TaskExecutionRequest TypedDict structure."""
        request: TaskExecutionRequest = {
            "workflowId": "workflow-123",
            "taskId": "task-a",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:task-a",
            "expectedVersion": 0,
            "deadlineMs": 30000,
            "correlationId": "correlation-456",
        }

        assert request["workflowId"] == "workflow-123"
        assert request["taskId"] == "task-a"
        assert request["targetLambdaArn"] == "arn:aws:lambda:us-east-1:123456789012:function:task-a"
        assert request["expectedVersion"] == 0
        assert request["deadlineMs"] == 30000
        assert request["correlationId"] == "correlation-456"

    def test_start_workflow_request_structure(self) -> None:
        """Test StartWorkflowRequest TypedDict structure."""
        graph: dict[str, TaskDefinition] = {
            "A": {
                "taskId": "A",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
                "dependsOn": [],
            },
            "B": {
                "taskId": "B",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b",
                "dependsOn": ["A"],
            },
        }

        start_request: StartWorkflowRequest = {
            "workflowId": "workflow-789",
            "graph": graph,
        }

        assert start_request["workflowId"] == "workflow-789"
        assert start_request["graph"] == graph
        assert "A" in start_request["graph"]
        assert "B" in start_request["graph"]
        assert start_request["graph"]["A"]["dependsOn"] == []
        assert start_request["graph"]["B"]["dependsOn"] == ["A"]

    def test_complex_workflow_graph(self) -> None:
        """Test a complex workflow graph similar to the Orchestra pattern."""
        # A → (B1, B2, B3) → C pattern
        graph: dict[str, TaskDefinition] = {
            "A": {
                "taskId": "A",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-a",
                "dependsOn": [],
            },
            "B1": {
                "taskId": "B1",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b1",
                "dependsOn": ["A"],
            },
            "B2": {
                "taskId": "B2",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b2",
                "dependsOn": ["A"],
            },
            "B3": {
                "taskId": "B3",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-b3",
                "dependsOn": ["A"],
            },
            "C": {
                "taskId": "C",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:lambda-c",
                "dependsOn": ["B1", "B2", "B3"],
            },
        }

        start_request: StartWorkflowRequest = {
            "workflowId": "orchestra-workflow",
            "graph": graph,
        }

        # Verify the structure
        assert len(start_request["graph"]) == 5

        # Verify A has no dependencies
        assert start_request["graph"]["A"]["dependsOn"] == []

        # Verify B tasks depend on A
        for task_id in ["B1", "B2", "B3"]:
            assert start_request["graph"][task_id]["dependsOn"] == ["A"]

        # Verify C depends on all B tasks
        assert set(start_request["graph"]["C"]
                   ["dependsOn"]) == {"B1", "B2", "B3"}

    def test_task_execution_request_serialization(self) -> None:
        """Test that TaskExecutionRequest can be serialized to JSON."""
        import json

        request: TaskExecutionRequest = {
            "workflowId": "workflow-123",
            "taskId": "task-a",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:task-a",
            "expectedVersion": 0,
            "deadlineMs": 30000,
            "correlationId": "correlation-456",
        }

        # Should be serializable to JSON
        json_str = json.dumps(request)

        # Should be deserializable back
        deserialized = json.loads(json_str)

        assert deserialized == request
        assert deserialized["workflowId"] == "workflow-123"
        assert deserialized["expectedVersion"] == 0

    @pytest.mark.parametrize("status", [
        "PENDING",
        "READY",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "CANCELED",
    ])
    def test_status_values_parameterized(self, status: Status) -> None:
        """Test each status value individually."""
        assert isinstance(status, str)
        assert len(status) > 0
        assert status.isupper()

    def test_task_definition_validation(self) -> None:
        """Test validation of TaskDefinition fields."""
        # Valid task definition
        task_def: TaskDefinition = {
            "taskId": "valid-task-123",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "dependsOn": ["dependency1", "dependency2"],
        }

        # Test task ID
        assert task_def["taskId"]
        assert isinstance(task_def["taskId"], str)

        # Test Lambda ARN format
        arn = task_def["targetLambdaArn"]
        assert arn.startswith("arn:aws:lambda:")
        assert ":function:" in arn

        # Test dependencies
        assert isinstance(task_def["dependsOn"], list)
        for dep in task_def["dependsOn"]:
            assert isinstance(dep, str)

    def test_edge_cases(self) -> None:
        """Test edge cases and boundary conditions."""
        # Empty workflow
        empty_start_request: StartWorkflowRequest = {
            "workflowId": "empty-workflow",
            "graph": {},
        }
        assert len(empty_start_request["graph"]) == 0

        # Single task workflow
        single_task_graph: dict[str, TaskDefinition] = {
            "ONLY": {
                "taskId": "ONLY",
                "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:only",
                "dependsOn": [],
            },
        }

        single_start_request: StartWorkflowRequest = {
            "workflowId": "single-task-workflow",
            "graph": single_task_graph,
        }
        assert len(single_start_request["graph"]) == 1
        assert single_start_request["graph"]["ONLY"]["dependsOn"] == []

    def test_type_safety(self) -> None:
        """Test type safety of the TypedDict definitions."""
        # This test primarily exists to ensure mypy type checking works correctly

        # TaskExecutionRequest with all required fields
        req: TaskExecutionRequest = {
            "workflowId": "test",
            "taskId": "test",
            "targetLambdaArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
            "expectedVersion": 0,
            "deadlineMs": 1000,
            "correlationId": "test",
        }

        # Accessing fields should work
        workflow_id: str = req["workflowId"]
        task_id: str = req["taskId"]
        version: int = req["expectedVersion"]
        deadline: int = req["deadlineMs"]

        assert isinstance(workflow_id, str)
        assert isinstance(task_id, str)
        assert isinstance(version, int)
        assert isinstance(deadline, int)
