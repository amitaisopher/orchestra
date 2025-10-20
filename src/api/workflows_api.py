from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["TABLE_NAME"]
ORCHESTRATOR_ARN = os.environ["ORCHESTRATOR_ARN"]

ddb = boto3.resource("dynamodb")
_table = ddb.Table(TABLE_NAME)
_lambda = boto3.client("lambda")


def _convert_decimals(obj: Any) -> Any:
    """Convert Decimal objects to int/float for JSON serialization."""
    if isinstance(obj, list):
        return [_convert_decimals(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: _convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        # Convert to int if it's a whole number, otherwise float
        return int(obj) if obj % 1 == 0 else float(obj)
    else:
        return obj


def _resp(status: int, body: dict[str, Any] | list[dict[str, Any]] | str) -> dict[str, Any]:
    # Convert any Decimal objects before JSON serialization
    converted_body = _convert_decimals(body)
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
        },
        "body": json.dumps(converted_body),
    }


def _query_workflow(workflow_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    pk = f"WORKFLOW#{workflow_id}"
    items: list[dict[str, Any]] = _table.query(
        KeyConditionExpression=Key("pk").eq(pk)).get("Items", [])
    meta = next((i for i in items if i.get("sk") == "META#WORKFLOW"), None)
    tasks = [i for i in items if i.get("type") == "TASK"]
    return meta, tasks


def _post_workflows(event: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "Invalid JSON"})

    workflow_id = (data.get("workflowId") or "").strip()
    if not workflow_id:
        return _resp(400, {"error": "workflowId is required"})

    try:
        payload: dict[str, Any] = {"mode": "start", "workflowId": workflow_id}
        if isinstance(data.get("lambdas"), dict):
            payload["lambdas"] = data["lambdas"]

        print(f"Invoking orchestrator for workflow {workflow_id}")
        print(f"Payload: {json.dumps(payload)}")

        response = _lambda.invoke(
            FunctionName=ORCHESTRATOR_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )

        print(f"Orchestrator response: {response}")

        # Check for errors in the orchestrator response
        if response.get("FunctionError"):
            error_payload = response.get("Payload", b"").read().decode("utf-8")
            print(
                f"Orchestrator error for workflow {workflow_id}: {error_payload}")
            return _resp(500, {"error": f"Failed to start workflow: {error_payload}"})

        # Read and log the response payload
        response_payload = response.get("Payload", b"").read().decode("utf-8")
        print(f"Orchestrator response payload: {response_payload}")

        print(f"Successfully invoked orchestrator for workflow {workflow_id}")
        return _resp(202, {"ok": True, "workflowId": workflow_id})

    except Exception as e:
        print(
            f"Error invoking orchestrator for workflow {workflow_id}: {str(e)}")
        return _resp(500, {"error": f"Failed to start workflow: {str(e)}"})


def _get_workflows() -> dict[str, Any]:
    resp = _table.scan(
        ProjectionExpression="#pk, sk, #s",
        ExpressionAttributeNames={"#pk": "pk", "#s": "status"},
    )
    metas = [i for i in resp.get(
        "Items", []) if i.get("sk") == "META#WORKFLOW"]
    workflows = []
    for meta in metas:
        # Extract workflow ID from pk field (format: "WORKFLOW#{workflow_id}")
        pk = meta.get("pk", "")
        workflow_id = pk.split("#", 1)[1] if pk.startswith("WORKFLOW#") else ""
        if workflow_id:
            workflows.append({
                "workflowId": workflow_id,
                "status": meta.get("status"),
            })
    return _resp(200, workflows)


def _get_workflow_by_id(path_params: dict[str, Any]) -> dict[str, Any]:
    workflow_id = (path_params or {}).get("id")
    if not workflow_id:
        return _resp(400, {"error": "Missing id"})

    try:
        meta, tasks = _query_workflow(workflow_id)
        if not meta:
            return _resp(404, {"error": f"Workflow {workflow_id} not found"})

        # Use hardcoded DAG for now - you can replace this with actual DAG from meta later
        dag = {"A": ["B1", "B2", "B3"], "B1": [
            "C"], "B2": ["C"], "B3": ["C"], "C": []}

        return _resp(200, {
            "workflowId": workflow_id,
            "status": meta.get("status"),
            "tasks": tasks,
            "dag": dag,
        })
    except Exception as e:
        # Log the error for debugging
        print(
            f"Error in _get_workflow_by_id for workflow {workflow_id}: {str(e)}")
        return _resp(500, {"error": "Internal server error"})


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    method = event.get("httpMethod")
    path = event.get("path", "")
    resource = event.get("resource", "")

    # Handle CORS preflight requests
    if method == "OPTIONS":
        return _resp(200, {})

    # Handle both proxy and non-proxy path formats
    if method == "POST" and (path == "/workflows" or resource == "/workflows"):
        return _post_workflows(event)
    if method == "GET" and (path == "/workflows" or resource == "/workflows"):
        return _get_workflows()
    if method == "GET" and (path.startswith("/workflows/") or resource == "/workflows/{id}"):
        # For proxy integration, extract ID from path
        if path.startswith("/workflows/"):
            workflow_id = path.split("/workflows/")[1]
            return _get_workflow_by_id({"id": workflow_id})
        else:
            # For non-proxy integration, use pathParameters
            return _get_workflow_by_id(event.get("pathParameters") or {})
    return _resp(404, {"error": "Route not found"})
