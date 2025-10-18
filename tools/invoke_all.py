from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import boto3

LAMBDA_NAMES = {
    "A": os.environ.get("LAMBDA_A_NAME", "PayloadStack-OrchestrationStack-LambdaA"),
    "B1": os.environ.get("LAMBDA_B1_NAME", "PayloadStack-OrchestrationStack-LambdaB1"),
    "B2": os.environ.get("LAMBDA_B2_NAME", "PayloadStack-OrchestrationStack-LambdaB2"),
    "B3": os.environ.get("LAMBDA_B3_NAME", "PayloadStack-OrchestrationStack-LambdaB3"),
    "C": os.environ.get("LAMBDA_C_NAME", "PayloadStack-OrchestrationStack-LambdaC"),
}


def _invoke_lambda(client, function_name: str) -> dict[str, Any]:
    resp = client.invoke(FunctionName=function_name, InvocationType="RequestResponse")
    payload = resp.get("Payload")
    return json.loads(payload.read().decode("utf-8")) if payload else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke all lambdas and run orchestrations")
    parser.add_argument("--state-machine-arn", required=False)
    parser.add_argument("--orchestrator-arn", required=False)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION"))
    args = parser.parse_args()

    lambda_client = boto3.client("lambda", region_name=args.region)
    sfn = boto3.client("stepfunctions", region_name=args.region)

    print("\n=== Directly invoking individual Lambdas (smoke test) ===")
    for k, name in LAMBDA_NAMES.items():
        try:
            out = _invoke_lambda(lambda_client, name)
            print(k, out)
        except Exception as exc:  # noqa: BLE001
            print(k, "ERROR:", exc)

    # Step Functions execution
    if args.state_machine_arn:
        print("\n=== Step Functions execution ===")
        exec_resp = sfn.start_execution(stateMachineArn=args.state_machine_arn, input=json.dumps({}))
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
        # Resolve ARNs for all functions
        lam = boto3.client("lambda", region_name=args.region)
        for k, name in LAMBDA_NAMES.items():
            conf = lam.get_function(FunctionName=name)
            lambdas[k] = conf["Configuration"]["FunctionArn"]
        payload = {"mode": "start", "workflowId": workflow_id, "lambdas": lambdas}
        lam.invoke(FunctionName=orchestrator, InvocationType="RequestResponse", 
                   Payload=json.dumps(payload).encode("utf-8"))
        print("Started DDB workflow:", workflow_id)
        print("(Inspect DynamoDB table to see task states transition)")


if __name__ == "__main__":
    main()