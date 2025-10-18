from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.client import BaseClient

from .workflow_types import TaskExecutionRequest

TABLE_NAME = os.environ["TABLE_NAME"]

ddb: BaseClient = boto3.client("dynamodb")
lambda_client: BaseClient = boto3.client("lambda")


def _pk(workflow_id: str) -> str:
    return f"WORKFLOW#{workflow_id}"


def _sk_task(task_id: str) -> str:
    return f"TASK#{task_id}"


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Executes a READY task: mark RUNNING → invoke target → mark SUCCEEDED/FAILED.

    Idempotency is enforced via conditional updates on the expected version & status.
    """
    # Event is a TaskExecutionRequest
    req = TaskExecutionRequest(**event)  # type: ignore[arg-type]

    # Mark RUNNING if status == READY and version matches expectedVersion
    try:
        ddb.update_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": _pk(req["workflowId"])}, "sk": {"S": _sk_task(req["taskId"]) }},
            UpdateExpression="SET #s = :running, version = version + :one",
            ConditionExpression="#s = :ready AND version = :ver",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":running": {"S": "RUNNING"},
                ":ready": {"S": "READY"},
                ":one": {"N": "1"},
                ":ver": {"N": str(req["expectedVersion"])},
            },
        )
    except ddb.exceptions.ConditionalCheckFailedException:  # type: ignore[attr-defined]
        # Another worker beat us or task not ready – treat as no-op
        return {"ok": False, "reason": "Not READY or version mismatch"}

    # Invoke target function synchronously
    start = time.time()
    try:
        resp = lambda_client.invoke(
            FunctionName=req["targetLambdaArn"],
            InvocationType="RequestResponse",
            Payload=json.dumps({"workflowId": req["workflowId"], "taskId": req["taskId"]}).encode(
                "utf-8",
            ),
        )
        payload = resp.get("Payload")
        result = json.loads(payload.read().decode("utf-8")) if payload else {}
        duration_ms = int((time.time() - start) * 1000)
        ddb.update_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": _pk(req["workflowId"])}, "sk": {"S": _sk_task(req["taskId"]) }},
            UpdateExpression="SET #s = :succeeded, #res = :res, durationMs = :dur",
            ExpressionAttributeNames={"#s": "status", "#res": "result"},
            ExpressionAttributeValues={
                ":succeeded": {"S": "SUCCEEDED"},
                ":res": {"S": json.dumps(result)},
                ":dur": {"N": str(duration_ms)},
            },
        )
        return {"ok": True, "status": "SUCCEEDED", "durationMs": duration_ms}
    except Exception as exc:  # noqa: BLE001
        ddb.update_item(
            TableName=TABLE_NAME,
            Key={"pk": {"S": _pk(req["workflowId"])}, "sk": {"S": _sk_task(req["taskId"]) }},
            UpdateExpression="SET #s = :failed, error = :err",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":failed": {"S": "FAILED"},
                ":err": {"S": json.dumps({"message": str(exc)})},
            },
        )
        return {"ok": False, "status": "FAILED", "error": str(exc)}