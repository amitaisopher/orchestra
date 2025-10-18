from __future__ import annotations

from typing import Literal, TypedDict

Status = Literal["PENDING", "READY", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"]


class TaskDefinition(TypedDict):
  taskId: str
  targetLambdaArn: str
  dependsOn: list[str]


class StartWorkflowRequest(TypedDict):
  workflowId: str
  graph: dict[str, TaskDefinition]


class TaskExecutionRequest(TypedDict):
  workflowId: str
  taskId: str
  targetLambdaArn: str
  expectedVersion: int
  deadlineMs: int
  correlationId: str