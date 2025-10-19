from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError


# Lazy environment variable access for testing compatibility
def _get_table_name() -> str:
    return os.environ.get("TABLE_NAME", "test-table")


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
    # Event is a TaskExecutionRequest - access as dict
    workflow_id = event["workflowId"]
    task_id = event["taskId"]
    target_lambda_arn = event["targetLambdaArn"]
    expected_version = event["expectedVersion"]

    # Mark RUNNING if status == READY and version matches expectedVersion
    try:
        ddb.update_item(
            TableName=_get_table_name(),
            Key={"pk": {"S": _pk(workflow_id)}, "sk": {
                "S": _sk_task(task_id)}},
            UpdateExpression="SET #s = :running, version = version + :one",
            ConditionExpression="#s = :ready AND version = :ver",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":running": {"S": "RUNNING"},
                ":ready": {"S": "READY"},
                ":one": {"N": "1"},
                ":ver": {"N": str(expected_version)},
            },
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # Another worker beat us or task not ready – treat as no-op
            return {"ok": False, "reason": "Not READY or version mismatch"}
        raise

    # Invoke target function synchronously
    start = time.time()
    try:
        resp = lambda_client.invoke(
            FunctionName=target_lambda_arn,
            InvocationType="RequestResponse",
            Payload=json.dumps(
                {"workflowId": workflow_id, "taskId": task_id}).encode("utf-8"),
        )
        payload = resp.get("Payload")
        result = json.loads(payload.read().decode("utf-8")) if payload else {}
        duration_ms = int((time.time() - start) * 1000)
        ddb.update_item(
            TableName=_get_table_name(),
            Key={"pk": {"S": _pk(workflow_id)}, "sk": {
                "S": _sk_task(task_id)}},
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
            TableName=_get_table_name(),
            Key={"pk": {"S": _pk(workflow_id)}, "sk": {
                "S": _sk_task(task_id)}},
            UpdateExpression="SET #s = :failed, error = :err",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":failed": {"S": "FAILED"},
                ":err": {"S": json.dumps({"message": str(exc)})},
            },
        )
        return {"ok": False, "status": "FAILED", "error": str(exc)}
