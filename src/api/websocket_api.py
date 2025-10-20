from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

CONNECTIONS_TABLE = os.environ["CONNECTIONS_TABLE"]
TABLE_NAME = os.environ["TABLE_NAME"]

dynamodb = boto3.resource("dynamodb")
connections_table = dynamodb.Table(CONNECTIONS_TABLE)
workflow_table = dynamodb.Table(TABLE_NAME)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle WebSocket connection events"""
    route_key = event.get("requestContext", {}).get("routeKey")
    connection_id = event.get("requestContext", {}).get("connectionId")

    try:
        if route_key == "$connect":
            return handle_connect(connection_id, event)
        elif route_key == "$disconnect":
            return handle_disconnect(connection_id)
        else:
            return {"statusCode": 400, "body": "Unknown route"}
    except Exception as e:
        print(f"Error handling WebSocket event: {e}")
        return {"statusCode": 500, "body": "Internal server error"}


def handle_connect(connection_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """Store WebSocket connection"""
    try:
        # Extract any subscription preferences from query parameters
        query_params = event.get("queryStringParameters") or {}
        workflow_id = query_params.get("workflowId")

        connections_table.put_item(
            Item={
                "connectionId": connection_id,
                "workflowId": workflow_id,  # Subscribe to specific workflow or all
                "timestamp": int(time.time()),
            },
        )
        print(f"Connected: {connection_id}")
        return {"statusCode": 200}
    except Exception as e:
        print(f"Error connecting: {e}")
        return {"statusCode": 500}


def handle_disconnect(connection_id: str) -> dict[str, Any]:
    """Remove WebSocket connection"""
    try:
        connections_table.delete_item(Key={"connectionId": connection_id})
        print(f"Disconnected: {connection_id}")
        return {"statusCode": 200}
    except Exception as e:
        print(f"Error disconnecting: {e}")
        return {"statusCode": 500}


def send_to_connection(connection_id: str, message: dict[str, Any], api_gateway_endpoint: str) -> bool:
    """Send message to specific WebSocket connection"""
    try:
        apigateway_client = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=api_gateway_endpoint,
        )

        apigateway_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message),
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "GoneException":
            # Connection is stale, remove it
            try:
                connections_table.delete_item(
                    Key={"connectionId": connection_id})
            except Exception:
                pass
        print(f"Error sending to {connection_id}: {e}")
        return False


def broadcast_workflow_update(
    workflow_id: str,
    workflow_data: dict[str, Any],
    api_gateway_endpoint: str,
) -> None:
    """Broadcast workflow update to all subscribed connections"""
    try:
        # Get all connections (or filter by workflowId if needed)
        response = connections_table.scan()
        connections = response.get("Items", [])

        message = {
            "type": "workflow_update",
            "workflowId": workflow_id,
            "data": workflow_data,
            "timestamp": int(time.time() * 1000),
        }

        for conn in connections:
            conn_id = conn["connectionId"]
            conn_workflow = conn.get("workflowId")

            # Send if connection subscribes to this workflow or all workflows
            if not conn_workflow or conn_workflow == workflow_id:
                send_to_connection(conn_id, message, api_gateway_endpoint)

    except Exception as e:
        print(f"Error broadcasting: {e}")
