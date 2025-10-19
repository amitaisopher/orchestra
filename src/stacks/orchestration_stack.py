from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_lambda_nodejs as lambda_node
from aws_cdk import aws_logs as logs
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

# adjust if using yarn/pnpm
LOCK_FILE_PATH = str(Path(__file__).resolve().parents[2] / "package-lock.json")


class OrchestrationStack(Stack):
    """Defines the five task Lambdas and both orchestration modes.

    Exposes:
      - self.state_machine (Step Functions)
      - self.all_functions (list of all Lambda functions)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        workflow_state_table: dynamodb.Table,
        ecr_repo: ecr.Repository,  # kept for future use if you want to pin images; unused here
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # === Common policies (least privilege for logs + X-Ray) ===
        logs_policy: iam.ManagedPolicy = iam.ManagedPolicy(
            self,
            "BasicLambdaLogs",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "xray:PutTraceSegments",
                        "xray:PutTelemetryRecords",
                    ],
                    resources=["*"],
                ),
            ],
        )

        # === Helper to attach policy to a Lambda role if present ===
        def _attach_logs_policy(fn: _lambda.IFunction) -> None:
            role = getattr(fn, "role", None)
            if role is not None:
                role.add_managed_policy(logs_policy)

        # === Task Lambdas ===
        # Node Lambdas (A, B1, C)
        def node_lambda(id_: str, entry: str) -> _lambda.Function:
            fn = lambda_node.NodejsFunction(
                self,
                id_,
                entry=entry,
                handler="handler",
                runtime=_lambda.Runtime.NODEJS_18_X,
                timeout=Duration.seconds(30),
                memory_size=256,
                log_group=logs.LogGroup(self, f"{id_}LogGroup",
                                        retention=logs.RetentionDays.THREE_MONTHS),
                tracing=_lambda.Tracing.ACTIVE,
                deps_lock_file_path=LOCK_FILE_PATH,
                bundling=lambda_node.BundlingOptions(
                    force_docker_bundling=False,
                    # Use local bundling when possible to avoid Docker permission issues
                ),
            )
            _attach_logs_policy(fn)
            return fn

        lambda_a = node_lambda(
            "LambdaA", "src/lambdas/node/lambda_a/index.mjs")
        lambda_b1 = node_lambda(
            "LambdaB1", "src/lambdas/node/lambda_b1/index.mjs")
        lambda_c = node_lambda(
            "LambdaC", "src/lambdas/node/lambda_c/index.mjs")

        # Python Lambda (B2)
        lambda_b2 = _lambda.Function(
            self,
            "LambdaB2",
            code=_lambda.Code.from_asset("src/lambdas/python/lambda_b2"),
            handler="handler.handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                "LambdaB2LogGroup",
                retention=logs.RetentionDays.THREE_MONTHS,
            ),
            tracing=_lambda.Tracing.ACTIVE,
        )
        _attach_logs_policy(lambda_b2)

        # Container Lambda (B3) - Python in container with RIC
        # CDK will build & publish an image asset automatically.
        lambda_b3 = _lambda.DockerImageFunction(
            self,
            "LambdaB3",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="src/lambdas/container_b3",
                file="Dockerfile",
            ),
            timeout=Duration.seconds(30),
            memory_size=512,
            log_group=logs.LogGroup(
                self,
                "LambdaB3LogGroup",
                retention=logs.RetentionDays.THREE_MONTHS,
            ),
            tracing=_lambda.Tracing.ACTIVE,
        )
        _attach_logs_policy(lambda_b3)

        self.all_functions: list[_lambda.IFunction] = [
            lambda_a,
            lambda_b1,
            lambda_b2,
            lambda_b3,
            lambda_c,
        ]

        # === Step Functions definition ===
        invoke_a = tasks.LambdaInvoke(
            self, "Invoke A", lambda_function=lambda_a, output_path="$.Payload",
        )
        invoke_b1 = tasks.LambdaInvoke(
            self, "Invoke B1", lambda_function=lambda_b1, output_path="$.Payload",
        )
        invoke_b2 = tasks.LambdaInvoke(
            self, "Invoke B2", lambda_function=lambda_b2, output_path="$.Payload",
        )
        invoke_b3 = tasks.LambdaInvoke(
            self, "Invoke B3", lambda_function=lambda_b3, output_path="$.Payload",
        )
        invoke_c = tasks.LambdaInvoke(
            self, "Invoke C", lambda_function=lambda_c, output_path="$.Payload",
        )

        parallel_b = sfn.Parallel(self, "Parallel B")
        parallel_b.branch(invoke_b1)
        parallel_b.branch(invoke_b2)
        parallel_b.branch(invoke_b3)

        definition = invoke_a.next(parallel_b).next(invoke_c)

        # Role for Step Functions with least-privilege Lambda invoke
        sfn_role = iam.Role(
            self,
            "StateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={
                "InvokeSpecificLambdas": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[
                                fn.function_arn for fn in self.all_functions],
                        ),
                    ],
                ),
            },
        )

        self.state_machine = sfn.StateMachine(
            self,
            "WorkflowStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(5),
            role=sfn_role,
            tracing_enabled=True,
        )

        # === DDB-driven Orchestrator/Worker Lambdas ===

        # ------------------------------------------------------------
        # 1️⃣ Define ROOT and CODE_ROOT
        # ------------------------------------------------------------
        # points to your project root
        ROOT = Path(__file__).resolve().parents[2]
        # where your ddb_workflow package lives
        CODE_ROOT = str(ROOT / "src")
        # ------------------------------------------------------------

        orchestrator = _lambda.Function(
            self,
            "OrchestratorLambda",
            code=_lambda.Code.from_asset(CODE_ROOT),
            handler="ddb_workflow.orchestrator_lambda.handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "TABLE_NAME": workflow_state_table.table_name,
                "WORKER_ARN": "to_be_patched",
                # Pass task ARNs so orchestrator can start workflows directly
                "LAMBDA_A_ARN": lambda_a.function_arn,
                "LAMBDA_B1_ARN": lambda_b1.function_arn,
                "LAMBDA_B2_ARN": lambda_b2.function_arn,
                "LAMBDA_B3_ARN": lambda_b3.function_arn,
                "LAMBDA_C_ARN": lambda_c.function_arn,
            },
            log_group=logs.LogGroup(
                self,
                "OrchestratorLogGroup",
                retention=logs.RetentionDays.THREE_MONTHS,
            ),
            tracing=_lambda.Tracing.ACTIVE,
        )
        _attach_logs_policy(orchestrator)
        self.orchestrator = orchestrator

        worker = _lambda.Function(
            self,
            "WorkerLambda",
            code=_lambda.Code.from_asset(CODE_ROOT),
            handler="ddb_workflow.worker_lambda.handler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "TABLE_NAME": workflow_state_table.table_name,
                "LAMBDA_A_ARN": lambda_a.function_arn,
                "LAMBDA_B1_ARN": lambda_b1.function_arn,
                "LAMBDA_B2_ARN": lambda_b2.function_arn,
                "LAMBDA_B3_ARN": lambda_b3.function_arn,
                "LAMBDA_C_ARN": lambda_c.function_arn,
            },
            log_group=logs.LogGroup(
                self,
                "WorkerLogGroup",
                retention=logs.RetentionDays.THREE_MONTHS,
            ),
            tracing=_lambda.Tracing.ACTIVE,
        )
        _attach_logs_policy(worker)

        # Patch orchestrator env with real worker ARN
        orchestrator.add_environment("WORKER_ARN", worker.function_arn)

        # Least-privilege permissions
        workflow_state_table.grant_read_write_data(orchestrator)
        workflow_state_table.grant_read_write_data(worker)

        # Worker can invoke only the five task Lambdas
        for fn in self.all_functions:
            fn.grant_invoke(worker)

        # Orchestrator can invoke only the Worker
        worker.grant_invoke(orchestrator)

        # DynamoDB Streams -> Orchestrator (using event source helper)
        orchestrator.add_event_source(
            lambda_event_sources.DynamoEventSource(
                workflow_state_table,
                starting_position=_lambda.StartingPosition.TRIM_HORIZON,
                batch_size=10,
                bisect_batch_on_error=False,
                retry_attempts=2,
                parallelization_factor=1,
            ),
        )

        # === Outputs ===
        CfnOutput(self, "LambdaAName", value=lambda_a.function_name,
                  export_name=f"{self.stack_name}-LambdaA-Name")
        CfnOutput(self, "LambdaB1Name", value=lambda_b1.function_name,
                  export_name=f"{self.stack_name}-LambdaB1-Name")
        CfnOutput(self, "LambdaB2Name", value=lambda_b2.function_name,
                  export_name=f"{self.stack_name}-LambdaB2-Name")
        CfnOutput(self, "LambdaB3Name", value=lambda_b3.function_name,
                  export_name=f"{self.stack_name}-LambdaB3-Name")
        CfnOutput(self, "LambdaCName", value=lambda_c.function_name,
                  export_name=f"{self.stack_name}-LambdaC-Name")

        CfnOutput(self, "OrchestratorName", value=orchestrator.function_name,
                  export_name=f"{self.stack_name}-Orchestrator-Name")
        CfnOutput(self, "WorkerName", value=worker.function_name,
                  export_name=f"{self.stack_name}-Worker-Name")
        CfnOutput(self, "StateMachineArn", value=self.state_machine.state_machine_arn,
                  export_name=f"{self.stack_name}-StateMachine-Arn")
