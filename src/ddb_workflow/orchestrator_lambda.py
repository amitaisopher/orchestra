from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.client import BaseClient

from .workflow_types import TaskExecutionRequest

TABLE_NAME = os.environ["TABLE_NAME"]
WORKER_ARN = os.environ["WORKER_ARN"]

ddb: BaseClient = boto3.client("dynamodb")
ddb_res= boto3.resource("dynamodb")
table = ddb_res.Table(TABLE_NAME)
lambda_client: BaseClient = boto3.client("lambda")


def _pk(workflow_id: str) -> str:
    return f"WORKFLOW#{workflow_id}"


def _sk_meta() -> str:
    return "META#WORKFLOW"


def _sk_task(task_id: str) -> str:
    return f"TASK#{task_id}"




def _invoke_worker(req: TaskExecutionRequest) -> None:
    # Convert TaskExecutionRequest to serializable dict
    payload = {
        "workflowId": req["workflowId"],
        "taskId": req["taskId"], 
        "targetLambdaArn": req["targetLambdaArn"],
        "expectedVersion": req["expectedVersion"],
        "deadlineMs": req["deadlineMs"],
        "correlationId": req["correlationId"],
    }
    
    lambda_client.invoke(
        FunctionName=WORKER_ARN,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def _start_from_template(workflow_id: str, lambdas: dict[str, str]) -> None:
    """Seeds the A → (B1,B2,B3) → C workflow into DynamoDB and triggers A.

    Args:
        workflow_id: Correlation/workflow id.
        lambdas: Mapping of taskId to Lambda ARN (A,B1,B2,B3,C).
    """
    # Build items
    items: list[dict[str, Any]] = []

    # META item
    items.append(
        {
            "pk": _pk(workflow_id),
            "sk": _sk_meta(),
            "type": "META",
            "status": "PENDING",
        },
    )

    graph = {
        "A": {"dependsOn": [], "dependents": ["B1", "B2", "B3"], "target": lambdas["A"]},
        "B1": {"dependsOn": ["A"], "dependents": ["C"], "target": lambdas["B1"]},
        "B2": {"dependsOn": ["A"], "dependents": ["C"], "target": lambdas["B2"]},
        "B3": {"dependsOn": ["A"], "dependents": ["C"], "target": lambdas["B3"]},
        "C": {"dependsOn": ["B1", "B2", "B3"], "dependents": [], "target": lambdas["C"]},
    }

    for task_id, meta in graph.items():
        items.append(
            {
                "pk": _pk(workflow_id),
                "sk": _sk_task(task_id),
                "type": "TASK",
                "taskId": task_id,
                "status": "READY" if task_id == "A" else "PENDING",
                "dependsOn": ",".join(meta["dependsOn"]),
                "dependents": ",".join(meta["dependents"]),
                "remainingDeps": 0 if task_id == "A" else len(meta["dependsOn"]),
                "version": 0,
                "targetLambdaArn": meta["target"],
            },
        )

    # Write in a batch - remove _as_ddb_item() conversion
    with table.batch_writer() as batch:  # type: ignore[attr-defined]
        for it in items:
            batch.put_item(Item=it)  # ✅ Pass raw Python objects

    # Trigger A via worker
    _invoke_worker(
        TaskExecutionRequest(
            workflowId=workflow_id,
            taskId="A",
            targetLambdaArn=lambdas["A"],
            expectedVersion=0,
            deadlineMs=15000,
            correlationId=workflow_id,
        ),
    )


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Two modes:
    1) Direct invocation with { "mode": "start", "workflowId": "..." }
    2) DynamoDB Stream event to fan-out dependents when tasks complete
    
    Examle event for direct start:
    {
        "mode": "start",
        "workflowId": "blabla",
        "lambdas": {
            "A": "arn:aws:lambda:eu-central-1:757433692112:function:OrchestrationStack-LambdaAE814F098-R0A0TV2Szt8q",
            "B1": "arn:aws:lambda:eu-central-1:757433692112:function:OrchestrationStack-LambdaB15D9C358A-qBAgLuIrxURi",
            "B2": "arn:aws:lambda:eu-central-1:757433692112:function:OrchestrationStack-LambdaB216234463-VxFywx1PzEm9",
            "B3": "arn:aws:lambda:eu-central-1:757433692112:function:OrchestrationStack-LambdaB390451B38-QBzZtOU51lVj",
            "C": "arn:aws:lambda:eu-central-1:757433692112:function:OrchestrationStack-LambdaCAACE7A4E-z7cpMqDhFM5d"
        }
    }
    
    """
    # Direct start?
    if isinstance(event, dict) and event.get("mode") == "start":
        workflow_id = str(event["workflowId"])  # required
        # Lambdas ARNs must be provided by environment (passed via Worker env)
        lambdas = {
            "A": os.environ.get("LAMBDA_A_ARN", ""),
            "B1": os.environ.get("LAMBDA_B1_ARN", ""),
            "B2": os.environ.get("LAMBDA_B2_ARN", ""),
            "B3": os.environ.get("LAMBDA_B3_ARN", ""),
            "C": os.environ.get("LAMBDA_C_ARN", ""),
        }
        if not all(lambdas.values()):
            # In this minimal sample we rely on the test script to build the request with target ARNs
            lambdas = event.get("lambdas", {})
        _start_from_template(workflow_id, lambdas)  # seed + trigger A
        return {"ok": True, "workflowId": workflow_id}

    # Otherwise: DDB Streams fan-out
    # We expect records where a TASK transitioned to SUCCEEDED – decrement dependents' counters.
    for rec in event.get("Records", []):
        if rec.get("eventName") not in ("MODIFY", "INSERT"):
            continue
        new_img = rec.get("dynamodb", {}).get("NewImage", {})
        old_img = rec.get("dynamodb", {}).get("OldImage", {})
        if not new_img:
            continue
        typ = new_img.get("type", {}).get("S")
        status_new = new_img.get("status", {}).get("S")
        status_old = old_img.get("status", {}).get("S") if old_img else None
        if typ != "TASK" or status_new != "SUCCEEDED" or status_old == "SUCCEEDED":
            continue
        pk = new_img["pk"]["S"]
        workflow_id = pk.split("#", 1)[1]
        task_id = new_img["taskId"]["S"]
        dependents_csv = new_img.get("dependents", {}).get("S", "")
        if not dependents_csv:
            continue
        dependents = [x for x in dependents_csv.split(",") if x]
        # Decrement remainingDeps on each dependent; when it hits 0, mark READY and trigger worker
        for dep in dependents:
            # Atomically decrement remainingDeps if > 0
            try:
                resp = ddb.update_item(
                    TableName=TABLE_NAME,
                    Key={"pk": {"S": pk}, "sk": {"S": _sk_task(dep)}},
                    UpdateExpression="SET remainingDeps = remainingDeps - :one",
                    ConditionExpression="remainingDeps > :zero",
                    ExpressionAttributeValues={":one": {"N": "1"}, ":zero": {"N": "0"}},
                    ReturnValues="ALL_NEW",
                )
                new_vals = resp.get("Attributes", {})
                new_remaining = int(new_vals.get("remainingDeps", {}).get("N", "0"))
                if new_remaining == 0:
                    # Mark READY if PENDING
                    try:
                        upd = ddb.update_item(
                            TableName=TABLE_NAME,
                            Key={"pk": {"S": pk}, "sk": {"S": _sk_task(dep)}},
                            UpdateExpression="SET #s = :ready, version = version + :one",
                            ConditionExpression="#s = :pending",
                            ExpressionAttributeNames={"#s": "status"},
                            ExpressionAttributeValues={
                                ":ready": {"S": "READY"},
                                ":pending": {"S": "PENDING"},
                                ":one": {"N": "1"},
                            },
                            ReturnValues="ALL_NEW",
                        )
                        dep_target = new_vals.get("targetLambdaArn", {}).get("S")
                        dep_version = int(new_vals.get("version", {}).get("N", "0")) + 1
                        _invoke_worker(
                            TaskExecutionRequest(
                                workflowId=workflow_id,
                                taskId=dep,
                                targetLambdaArn=dep_target,
                                expectedVersion=dep_version,
                                deadlineMs=15000,
                                correlationId=workflow_id,
                            ),
                        )
                    except ddb.exceptions.ConditionalCheckFailedException:  # type: ignore[attr-defined]
                        pass
            except ddb.exceptions.ConditionalCheckFailedException:  # type: ignore[attr-defined]
                pass

    return {"ok": True}