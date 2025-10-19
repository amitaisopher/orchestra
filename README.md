
# Orchestra - AWS Lambda Workflow Orchestration System

A distributed workflow orchestration system built with AWS Lambda, DynamoDB, and CDK that demonstrates two different orchestration patterns: **Step Functions** and **DynamoDB-based event-driven orchestration**.

## Overview

Orchestra implements a simple workflow pattern: `A → (B1, B2, B3) → C` where:
- Task A executes first
- Tasks B1, B2, B3 execute in parallel after A completes
- Task C executes after all B tasks complete

The system demonstrates two orchestration approaches:
1. **AWS Step Functions** - Traditional state machine orchestration
2. **DynamoDB + Lambda** - Event-driven orchestration using DynamoDB Streams

## Architecture

### Components

- **Orchestrator Lambda**: Manages workflow state and dependency resolution
- **Worker Lambda**: Executes individual tasks with idempotency guarantees
- **Task Lambdas (A, B1, B2, B3, C)**: Business logic functions
- **DynamoDB Table**: Stores workflow state and task dependencies
- **Step Functions State Machine**: Alternative orchestration method

### Key Features

- **Idempotency**: Version-based optimistic locking prevents duplicate executions
- **Concurrency Control**: Multiple workers can safely process tasks simultaneously
- **Event-Driven**: Uses DynamoDB Streams for reactive coordination
- **Fault Tolerance**: Conditional updates ensure consistency

## Prerequisites

### 1. Install AWS CLI

```bash
# On macOS
brew install awscli

# On Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# On Windows
# Download and run the AWS CLI MSI installer from AWS website
```

### 2. Install AWS CDK

```bash
npm install -g aws-cdk
```

### 3. Configure AWS Credentials

```bash
# Configure AWS CLI with your credentials
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=eu-central-1
```

### 4. Install UV (Python Package Manager)

```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Setup Instructions

### 1. Clone and Setup Environment

```bash
git clone <repository-url>
cd orchestra

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### 2. Bootstrap CDK (First Time Only)

```bash
# Bootstrap CDK in your AWS account/region
uv run cdk bootstrap
```

### 3. Deploy Infrastructure

```bash
# Deploy the complete stack
uv run cdk deploy --all

# Or deploy specific stacks
uv run cdk deploy PayloadStack
uv run cdk deploy OrchestrationStack
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
AWS_REGION=eu-central-1
# Add other environment variables as needed
```

## Usage

### Running Workflows

Use the provided test script to execute workflows:

```bash
# Run with VS Code debugger (recommended)
# Use the launch configuration in .vscode/launch.json

# Or run directly
uv run python tools/invoke_all.py \
  --orchestrator-arn arn:aws:lambda:region:account:function:orchestrator \
  --region eu-central-1 \
  --stack-name OrchestrationStack
```

### VS Code Debugging

The project includes a VS Code launch configuration:

1. Open the project in VS Code
2. Go to Run and Debug (Ctrl+Shift+D)
3. Select "Python Debugger: Invoke All"
4. Enter the required parameters when prompted:
   - State Machine ARN (optional)
   - Orchestrator ARN
   - AWS Region
   - Stack Name

### Monitoring Workflows

1. **DynamoDB Console**: View workflow state and task progress
2. **CloudWatch Logs**: Monitor Lambda execution logs
3. **Step Functions Console**: Track Step Functions executions (if using SFN mode)

## Project Structure

```
orchestra/
├── src/
│   ├── ddb_workflow/
│   │   ├── orchestrator_lambda.py    # Workflow coordinator
│   │   ├── worker_lambda.py          # Task executor
│   │   └── workflow_types.py         # Type definitions
│   ├── lambdas/                      # Business logic functions
│   │   ├── node/
│   │   │   ├── lambda_a/
│   │   │   ├── lambda_b1/
│   │   │   └── lambda_c/
│   │   ├── python/
│   │   │   └── lambda_b2/
│   │   └── container_b3/
│   └── stacks/
│       ├── orchestration_stack.py    # Main CDK stack
│       ├── payload_stack.py          # Shared resources
│       └── monitoring_stack.py       # Monitoring resources
├── tools/
│   └── invoke_all.py                 # Test/execution script
├── .vscode/
│   └── launch.json                   # VS Code debug config
├── pyproject.toml
├── uv.lock
└── README.md
```

## How It Works

### DynamoDB-Based Orchestration

1. **Initialization**: Orchestrator seeds workflow graph in DynamoDB
2. **Task Execution**: Worker Lambda executes tasks with version-based locking
3. **Dependency Resolution**: DynamoDB Streams trigger fan-out when tasks complete
4. **State Management**: Conditional updates ensure exactly-once execution

### Workflow States

- **PENDING**: Task waiting for dependencies
- **READY**: Task ready for execution
- **RUNNING**: Task currently executing
- **SUCCEEDED**: Task completed successfully
- **FAILED**: Task execution failed

### Key Concepts

- **Version Control**: Optimistic locking prevents race conditions
- **Idempotency**: Tasks execute exactly once even with retries
- **Fan-out**: Orchestrator triggers dependent tasks when dependencies complete

## Task Implementation Examples

The project includes sample tasks implemented in different runtimes:

- **Lambda A** (Node.js): Simple function that returns workflow metadata
- **Lambda B1** (Node.js): Processes data and returns results
- **Lambda B2** (Python): Demonstrates Python-based task execution
- **Lambda B3** (Container): Shows containerized Lambda deployment
- **Lambda C** (Node.js): Final aggregation task

## Development Commands

```bash
# Install dependencies
uv pip install -r requirements.txt

# Run type checking
uv run mypy src/

# Run tests
uv run pytest

# Format code
uv run black src/ tools/
uv run isort src/ tools/

# Deploy infrastructure
uv run cdk deploy --all

# Destroy infrastructure
uv run cdk destroy --all

# View CDK diff
uv run cdk diff

# Synthesize CloudFormation
uv run cdk synth
```

## Configuration

### Environment Variables

The system uses the following environment variables:

- `AWS_REGION`: AWS region for deployment
- `TABLE_NAME`: DynamoDB table name (set by CDK)
- `WORKER_ARN`: Worker Lambda ARN (set by CDK)
- `LAMBDA_*_NAME`: Lambda function names (for testing)

### CDK Context

The CDK application can be configured via `cdk.json`:

```json
{
  "app": "python src/app.py",
  "context": {
    "@aws-cdk/core:enableStackNameDuplicates": true,
    "aws-cdk:enableDiffNoFail": true
  }
}
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure absolute imports in Lambda functions
   ```python
   # Good
   from ddb_workflow.workflow_types import TaskExecutionRequest
   
   # Bad
   from .workflow_types import TaskExecutionRequest
   ```

2. **Permission Errors**: Verify IAM roles have necessary permissions
   - DynamoDB read/write access
   - Lambda invoke permissions
   - CloudWatch Logs access

3. **Resource Not Found**: Check CloudFormation exports are created
   ```bash
   aws cloudformation list-exports --region eu-central-1
   ```

4. **Version Conflicts**: Ensure expected versions match in DynamoDB
   - Check task versions in DynamoDB console
   - Verify worker Lambda receives correct expected version

### Debugging Tips

1. **CloudWatch Logs**: Check logs for detailed error messages
   ```bash
   aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/"
   ```

2. **DynamoDB Console**: Inspect workflow state and task progress

3. **X-Ray Tracing**: Enable for distributed tracing (optional)

4. **VS Code Debugger**: Use for local testing and development

### Performance Tuning

- **Lambda Memory**: Adjust based on task requirements
- **DynamoDB Capacity**: Configure read/write capacity units
- **Timeout Settings**: Set appropriate timeouts for tasks
- **Batch Size**: Optimize DynamoDB Stream batch sizes

## Testing

### Unit Tests

```bash
# Run unit tests
uv run pytest tests/unit/

# Run with coverage
uv run pytest --cov=src tests/
```

### Integration Tests

```bash
# Deploy test stack
uv run cdk deploy --all

# Run integration tests
uv run python tools/invoke_all.py --orchestrator-arn <arn>

# Check DynamoDB for workflow completion
```

## Monitoring and Observability

### CloudWatch Metrics

The system exports custom metrics:
- Workflow execution duration
- Task success/failure rates
- Concurrent executions

### Alarms

Set up CloudWatch alarms for:
- Lambda errors
- DynamoDB throttling
- Workflow failures

### Dashboards

Create CloudWatch dashboards to monitor:
- Workflow throughput
- Task execution times
- System health

## Security Considerations

- **IAM Roles**: Follow principle of least privilege
- **VPC**: Deploy Lambdas in VPC if required
- **Encryption**: Enable encryption at rest for DynamoDB
- **Secrets**: Use AWS Secrets Manager for sensitive data

## Cost Optimization

- **Reserved Capacity**: Use for predictable DynamoDB workloads
- **Lambda Provisioned Concurrency**: For consistent performance
- **CloudWatch Log Retention**: Set appropriate retention periods
- **Resource Cleanup**: Destroy unused stacks

## Cleanup

To avoid AWS charges, destroy the infrastructure when done:

```bash
uv run cdk destroy --all
```

Verify all resources are deleted:
```bash
aws cloudformation list-stacks --stack-status-filter DELETE_COMPLETE
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add type hints for all functions
- Include docstrings for public methods
- Write tests for new functionality
- Update documentation as needed

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS CDK team for the excellent infrastructure-as-code framework
- AWS Lambda team for serverless compute capabilities
- DynamoDB team for the scalable NoSQL database
- UV team for the fast Python package manager
