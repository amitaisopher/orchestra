from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import boto3
from dotenv import load_dotenv

load_dotenv(".env")


def _invoke_lambda(client, function_name: str) -> dict[str, Any]:
    resp = client.invoke(FunctionName=function_name,
                         InvocationType="RequestResponse")
    payload = resp.get("Payload")
    if not payload:
        return {}

    payload_data = payload.read().decode("utf-8")
    if not payload_data.strip():
        return {}

    return json.loads(payload_data)


def get_lambda_names_from_exports(cloudformation_client, stack_name: str) -> dict[str, str]:
    """Get actual Lambda function names from CloudFormation exports."""
    try:
        exports = cloudformation_client.list_exports()["Exports"]
        lambda_names = {}

        export_mapping = {
            f"{stack_name}-LambdaA-Name": "A",
            f"{stack_name}-LambdaB1-Name": "B1",
            f"{stack_name}-LambdaB2-Name": "B2",
            f"{stack_name}-LambdaB3-Name": "B3",
            f"{stack_name}-LambdaC-Name": "C",
        }

        for export in exports:
            export_name = export["Name"]
            if export_name in export_mapping:
                key = export_mapping[export_name]
                lambda_names[key] = export["Value"]

        return lambda_names
    except Exception as exc:
        print(f"Failed to get exports: {exc}")
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoke all lambdas and run orchestrations")
    parser.add_argument("--state-machine-arn", required=False)
    parser.add_argument("--orchestrator-arn", required=False)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION"))
    parser.add_argument(
        "--stack-name", default="OrchestrationStack", help="CDK stack name for exports")

    args = parser.parse_args()

    lambda_client = boto3.client("lambda", region_name=args.region)
    sfn = boto3.client("stepfunctions", region_name=args.region)
    cfn = boto3.client("cloudformation", region_name=args.region)

    # Get actual Lambda names from CloudFormation exports
    lambda_names = get_lambda_names_from_exports(cfn, args.stack_name)
    if not lambda_names:
        print("Warning: Could not get Lambda names from exports, falling back to hardcoded names")
        # Fallback to hardcoded names for testing
        lambda_names = {
            "A": "orchestration-lambda-a",
            "B1": "orchestration-lambda-b1",
            "B2": "orchestration-lambda-b2",
            "B3": "orchestration-lambda-b3",
            "C": "orchestration-lambda-c",
        }

    # print("\n=== Directly invoking individual Lambdas (smoke test) ===")
    # for k, name in lambda_names.items():
    #     try:
    #         out = _invoke_lambda(lambda_client, name)
    #         print(k, out)
    #     except Exception as exc:
    #         print(k, "ERROR:", exc)

    # Step Functions execution
    if args.state_machine_arn:
        print("\n=== Step Functions execution ===")
        exec_resp = sfn.start_execution(
            stateMachineArn=args.state_machine_arn, input=json.dumps({}))
        exec_arn = exec_resp["executionArn"]
        print("Started:", exec_arn)
        while True:
            desc = sfn.describe_execution(executionArn=exec_arn)
            if desc["status"] in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
                print("Status:", desc["status"])
                if desc["status"] == "SUCCEEDED":
                    print("Output:", desc.get("output"))
                break
            time.sleep(2)

    # DynamoDB Orchestrator start
    if args.orchestrator_arn:
        print("\n=== DDB Orchestrator start ===")
        orchestrator = args.orchestrator_arn
        workflow_id = f"wf-{int(time.time())}"
        lambdas = {}
        lam = boto3.client("lambda", region_name=args.region)
        for k, name in lambda_names.items():  # Changed from LAMBDA_NAMES
            conf = lam.get_function(FunctionName=name)
            lambdas[k] = conf["Configuration"]["FunctionArn"]
        payload = {"mode": "start",
                   "workflowId": workflow_id, "lambdas": lambdas}
        lam.invoke(
            FunctionName=orchestrator,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        print("Started DDB workflow:", workflow_id)
        print("(Inspect DynamoDB table to see task states transition)")


if __name__ == "__main__":
    main()
