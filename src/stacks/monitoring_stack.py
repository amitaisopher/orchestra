from __future__ import annotations

from collections.abc import Iterable

from aws_cdk import Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class MonitoringStack(Stack):
    """CloudWatch dashboard and basic alarms for key components."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        functions: Iterable[_lambda.IFunction],
        state_machine: sfn.IStateMachine,
        table: dynamodb.ITable,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        dashboard = cw.Dashboard(self, "ServerlessOrchDashboard")

        # Lambda widgets
        for fn in functions:
            dashboard.add_widgets(
                cw.GraphWidget(
                    title=f"{fn.function_name} – Invocations/Errors",
                    left=[fn.metric_invocations()],
                    right=[fn.metric_errors()],
                ),
                cw.GraphWidget(
                    title=f"{fn.function_name} – Duration p95",
                    left=[fn.metric_duration(statistic="p95")],
                ),
            )

        # Step Functions widgets
        dashboard.add_widgets(
            cw.GraphWidget(
                title="State machine – Executions",
                left=[state_machine.metric_started()],
                right=[state_machine.metric_succeeded(), state_machine.metric_failed()],
            ),
        )

        # DynamoDB widgets
        dashboard.add_widgets(
            cw.GraphWidget(
                title="DynamoDB – Throttles/Errors",
                left=[
                    table.metric("ReadThrottleEvents"),
                    table.metric("WriteThrottleEvents"),
                ],
                right=[
                    table.metric_user_errors(),
                ],
            ),
        )