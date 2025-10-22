from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from .workflow_types import TaskExecutionRequest


def _get_table_name() -> str:
    return os.environ.get("TABLE_NAME", "test-table")


def _get_worker_arn() -> str:
    return os.environ.get("WORKER_ARN", "test-worker-arn")


def _get_websocket_api_url() -> str:
    return os.environ.get("WEBSOCKET_API_URL", "")


def _broadcast_workflow_update(workflow_id: str, workflow_data: dict) -> None:
    """Broadcast workflow status update to all connected WebSocket clients."""
    try:
        websocket_api_url = _get_websocket_api_url()
        if not websocket_api_url:
            print("WebSocket API URL not configured, skipping broadcast")
            return

        # Create API Gateway Management API client
        # Extract the API ID and stage from the WebSocket URL
        # URL format: wss://api-id.execute-api.region.amazonaws.com/stage
        url_parts = websocket_api_url.replace("wss://", "").split("/")
        api_id = url_parts[0].split(".")[0]
        stage = url_parts[1] if len(url_parts) > 1 else "prod"
        region = os.environ.get("AWS_REGION", "us-east-1")

        apigatewaymanagementapi = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}",
        )

        # Get all active connections from DynamoDB
        dynamodb = boto3.resource("dynamodb")
        connections_table_name = os.environ.get(
            "CONNECTIONS_TABLE_NAME", "WebSocketConnections",
        )
        connections_table = dynamodb.Table(connections_table_name)

        try:
            response = connections_table.scan()
            connections = response.get("Items", [])

            message = {
                "type": "workflow_update",
                "workflow_id": workflow_id,
                "data": workflow_data,
            }

            # Send message to all connected clients
            for connection in connections:
                connection_id = connection["connectionId"]
                try:
                    apigatewaymanagementapi.post_to_connection(
                        ConnectionId=connection_id,
                        Data=json.dumps(message),
                    )
                    print(f"Sent update to connection {connection_id}")
                except apigatewaymanagementapi.exceptions.GoneException:
                    # Connection is stale, remove it
                    print(
                        f"Removing stale connection {connection_id} (GoneException)")
                    connections_table.delete_item(
                        Key={"connectionId": connection_id},
                    )
                except Exception as e:
                    # Handle ForbiddenException (stale connection) and other errors
                    if "ForbiddenException" in str(e) or "Forbidden" in str(e):
                        print(
                            f"Removing stale connection {connection_id} (ForbiddenException)")
                        connections_table.delete_item(
                            Key={"connectionId": connection_id},
                        )
                    else:
                        print(
                            f"Error sending to connection {connection_id}: {e}")

        except Exception as e:
            print(f"Error querying connections: {e}")

    except Exception as e:
        print(f"Error broadcasting workflow update: {e}")


ddb: BaseClient = boto3.client("dynamodb")
ddb_res = boto3.resource("dynamodb")


def _get_workflow_state(workflow_id: str):
    """Get the current workflow state for broadcasting."""
    try:
        # Query all items for this workflow
        response = ddb.query(
            TableName=_get_table_name(),
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={
                ":pk": {"S": _pk(workflow_id)},
            },
        )

        items = response.get("Items", [])
        workflow_data = {
            "workflowId": workflow_id,
            "tasks": {},
            "status": "PENDING",
            "meta": {},
        }

        for item in items:
            if item.get("type", {}).get("S") == "META":
                workflow_data["status"] = item.get(
                    "status", {}).get("S", "PENDING")
            elif item.get("type", {}).get("S") == "TASK":
                task_id = item.get("taskId", {}).get("S", "")
                workflow_data["tasks"][task_id] = {
                    "taskId": task_id,
                    "status": item.get("status", {}).get("S", "PENDING"),
                    "dependsOn": item.get("dependsOn", {}).get("S", ""),
                    "dependents": item.get("dependents", {}).get("S", ""),
                    "remainingDeps": int(item.get("remainingDeps", {}).get("N", "0")),
                    "result": item.get("result", {}).get("S", ""),
                    "durationMs": int(item.get("durationMs", {}).get("N", "0")),
                }

        return workflow_data
    except Exception as e:
        print(f"Error getting workflow state for {workflow_id}: {e}")
        return {"workflowId": workflow_id, "tasks": {}, "status": "ERROR", "meta": {}}


def _get_table():
    return ddb_res.Table(_get_table_name())


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
        FunctionName=_get_worker_arn(),
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def _update_workflow_status(workflow_id: str) -> None:
    """Check all tasks and update overall workflow status."""
    try:
        # Query all tasks for this workflow
        response = _get_table().query(
            KeyConditionExpression="pk = :pk",
            FilterExpression="#type = :task_type",
            ExpressionAttributeNames={"#type": "type"},
            ExpressionAttributeValues={
                ":pk": _pk(workflow_id),
                ":task_type": "TASK",
            },
        )

        tasks = response.get("Items", [])
        if not tasks:
            return  # No tasks found

        task_statuses = [task.get("status") for task in tasks]

        # Determine overall workflow status based on task states
        if any(status == "FAILED" for status in task_statuses):
            # If any task failed, workflow is failed
            new_status = "FAILED"
        elif all(status == "SUCCEEDED" for status in task_statuses):
            # If all tasks succeeded, workflow is complete
            new_status = "SUCCEEDED"
        elif any(status in ["RUNNING", "READY"] for status in task_statuses):
            # If any task is running or ready to run, workflow is running
            new_status = "RUNNING"
        elif any(status in ["PENDING"] for status in task_statuses):
            # If tasks exist but none are active yet, workflow is still pending
            new_status = "PENDING"
        else:
            # Default fallback
            new_status = "PENDING"

        # Update the META workflow status
        try:
            ddb.update_item(
                TableName=_get_table_name(),
                Key={"pk": {"S": _pk(workflow_id)}, "sk": {"S": _sk_meta()}},
                UpdateExpression="SET #s = :status",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":status": {"S": new_status}},
                # Only update if record exists
                ConditionExpression="attribute_exists(pk)",
            )

            # Broadcast workflow status update via WebSocket
            workflow_data = {
                "workflow_id": workflow_id,
                "status": new_status,
                "tasks": [
                    {
                        "taskId": task.get("taskId", ""),
                        "status": task.get("status", ""),
                        "type": task.get("type", ""),
                    }
                    for task in tasks
                ],
            }
            _broadcast_workflow_update(workflow_id, workflow_data)

        except ClientError as e:
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                print(f"Error updating workflow status for {workflow_id}: {e}")

    except Exception as e:
        print(f"Error in _update_workflow_status for {workflow_id}: {e}")


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
    with _get_table().batch_writer() as batch:  # type: ignore[attr-defined]
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

    # Update workflow status after initial setup
    _update_workflow_status(workflow_id)


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
    print(f"Orchestrator handler called with event: {event}")

    # Direct start?
    if isinstance(event, dict) and event.get("mode") == "start":
        workflow_id = str(event["workflowId"])  # required
        print(f"Direct start mode for workflow: {workflow_id}")
        # Lambdas ARNs must be provided by environment (passed via Worker env)
        lambdas = {
            "A": os.environ.get("LAMBDA_A_ARN", ""),
            "B1": os.environ.get("LAMBDA_B1_ARN", ""),
            "B2": os.environ.get("LAMBDA_B2_ARN", ""),
            "B3": os.environ.get("LAMBDA_B3_ARN", ""),
            "C": os.environ.get("LAMBDA_C_ARN", ""),
        }
        if not all(lambdas.values()):
            # In this minimal sample we rely on the test script to build the request
            # with target ARNs
            lambdas = event.get("lambdas", {})
        print(f"Starting workflow {workflow_id} with lambdas: {lambdas}")
        _start_from_template(workflow_id, lambdas)  # seed + trigger A
        print(f"Successfully started workflow {workflow_id}")
        return {"ok": True, "workflowId": workflow_id}

    # Otherwise: DDB Streams fan-out
    # We expect records where a TASK transitioned to SUCCEEDED – decrement dependents' counters.
    print(
        f"Processing DynamoDB stream event with {len(event.get('Records', []))} records")
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

        # Handle task completion (SUCCEEDED) for dependency management
        if typ != "TASK" or status_new != "SUCCEEDED" or status_old == "SUCCEEDED":
            # Still update workflow status for any task status change (including FAILED)
            if typ == "TASK" and status_new in ["SUCCEEDED", "FAILED"] and status_old != status_new:
                pk = new_img["pk"]["S"]
                workflow_id = pk.split("#", 1)[1]
                print(
                    f"Task status changed for workflow {workflow_id}: {status_old} -> {status_new}")
                _update_workflow_status(workflow_id)
                # Broadcast WebSocket update for task status changes
                try:
                    print(
                        f"Attempting to broadcast WebSocket update for workflow {workflow_id}")
                    # Get current workflow data to broadcast
                    workflow_data = _get_workflow_state(workflow_id)
                    print(f"Got workflow data: {workflow_data}")
                    _broadcast_workflow_update(workflow_id, workflow_data)
                    print(
                        f"Successfully broadcasted WebSocket update for workflow {workflow_id}")
                except Exception as e:
                    print(
                        f"Error broadcasting workflow update for {workflow_id}: {e}")
            continue
        pk = new_img["pk"]["S"]
        workflow_id = pk.split("#", 1)[1]

        # Update overall workflow status whenever a task completes
        _update_workflow_status(workflow_id)

        # Broadcast WebSocket update for task completion
        try:
            print(
                f"Attempting to broadcast WebSocket update for task completion in workflow {workflow_id}")
            workflow_data = _get_workflow_state(workflow_id)
            print(f"Got workflow data for task completion: {workflow_data}")
            _broadcast_workflow_update(workflow_id, workflow_data)
            print(
                f"Successfully broadcasted WebSocket update for task completion in workflow {workflow_id}")
        except Exception as e:
            print(f"Error broadcasting workflow update for {workflow_id}: {e}")

        dependents_csv = new_img.get("dependents", {}).get("S", "")
        if not dependents_csv:
            continue
        dependents = [x for x in dependents_csv.split(",") if x]

        # Collect tasks that become ready for concurrent execution
        tasks_to_execute = []

        # Decrement remainingDeps on each dependent; collect tasks ready for execution
        for dep in dependents:
            # Atomically decrement remainingDeps if > 0
            try:
                resp = ddb.update_item(
                    TableName=_get_table_name(),
                    Key={"pk": {"S": pk}, "sk": {"S": _sk_task(dep)}},
                    UpdateExpression="SET remainingDeps = remainingDeps - :one",
                    ConditionExpression="remainingDeps > :zero",
                    ExpressionAttributeValues={
                        ":one": {"N": "1"}, ":zero": {"N": "0"}},
                    ReturnValues="ALL_NEW",
                )
                new_vals = resp.get("Attributes", {})
                new_remaining = int(new_vals.get(
                    "remainingDeps", {}).get("N", "0"))
                if new_remaining == 0:
                    # Mark READY if PENDING
                    try:
                        resp = ddb.update_item(
                            TableName=_get_table_name(),
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

                        new_vals_ready = resp.get("Attributes", {})
                        dep_target = new_vals_ready.get(
                            "targetLambdaArn", {}).get("S")
                        dep_version = int(new_vals_ready.get(
                            "version", {}).get("N", "0"))

                        # Collect task for concurrent execution instead of executing immediately
                        tasks_to_execute.append(TaskExecutionRequest(
                            workflowId=workflow_id,
                            taskId=dep,
                            targetLambdaArn=dep_target,
                            expectedVersion=dep_version,
                            deadlineMs=15000,
                            correlationId=workflow_id,
                        ))

                        print(
                            f"Task {dep} is now READY and queued for execution")

                    except ClientError as e:
                        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                            pass
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    pass

        # Execute all ready tasks concurrently (outside the dependency resolution loop)
        if tasks_to_execute:
            task_ids = [task['taskId'] for task in tasks_to_execute]
            print(
                f"Executing {len(tasks_to_execute)} tasks concurrently: {task_ids}")

            # Update workflow status once before executing tasks
            _update_workflow_status(workflow_id)

            # Broadcast WebSocket update for all tasks becoming ready
            try:
                workflow_data = _get_workflow_state(workflow_id)
                _broadcast_workflow_update(workflow_id, workflow_data)
            except Exception as e:
                print(
                    f"Error broadcasting workflow update for {workflow_id}: {e}")

            # Invoke all workers concurrently
            for task_req in tasks_to_execute:
                try:
                    _invoke_worker(task_req)
                    print(f"Invoked worker for task {task_req['taskId']}")
                except Exception as e:
                    print(
                        f"Error invoking worker for task {task_req['taskId']}: {e}")

    return {"ok": True}
