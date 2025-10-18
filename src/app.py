from __future__ import annotations

import os

from aws_cdk import App, Environment
from dotenv import load_dotenv

from src.stacks.monitoring_stack import MonitoringStack
from src.stacks.orchestration_stack import OrchestrationStack
from src.stacks.payload_stack import PayloadStack

load_dotenv(".env")


app: App = App()
AWS_ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", None)
AWS_REGION = os.environ.get("AWS_REGION", None)

print("#############################################################")
print(f"Deploying to account {AWS_ACCOUNT_ID} in region {AWS_REGION}")

# Adjust to your target account/region (or rely on CDK context/CLI)
env = Environment(account=AWS_ACCOUNT_ID, region=AWS_REGION)


payload = PayloadStack(app, "PayloadStack", env=env)


orchestration = OrchestrationStack(
    app,
    "OrchestrationStack",
    env=env,
    workflow_state_table=payload.workflow_state_table,
    ecr_repo=payload.b3_ecr_repo,
)


MonitoringStack(
    app,
    "MonitoringStack",
    env=env,
    functions=orchestration.all_functions,
    state_machine=orchestration.state_machine,
    table=payload.workflow_state_table,
)


app.synth()