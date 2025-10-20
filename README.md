
# Orchestra - AWS Lambda Workflow Orchestration System

A distributed workflow orchestration system with a web-based dashboard, built with AWS Lambda, DynamoDB, React, and CDK. The system demonstrates event-driven orchestration using DynamoDB Streams and provides a modern web interface for workflow management.

## Overview

Orchestra implements a workflow pattern: `A → (B1, B2, B3) → C` where:
- Task A executes first
- Tasks B1, B2, B3 execute in parallel after A completes
- Task C executes after all B tasks complete

The system includes:
1. **Backend**: Event-driven orchestration using DynamoDB Streams
2. **Frontend**: React-based workflow dashboard with real-time updates
3. **Infrastructure**: Multi-stack CDK deployment with API Gateway and S3 hosting

## Architecture

### Components

- **Workflow Dashboard**: React SPA hosted on S3 with automatic API configuration
- **API Gateway**: RESTful API for workflow management
- **Orchestrator Lambda**: Manages workflow state and dependency resolution
- **Worker Lambda**: Executes individual tasks with idempotency guarantees
- **Task Lambdas (A, B1, B2, B3, C)**: Business logic functions
- **DynamoDB Table**: Stores workflow state and task dependencies

### Deployment Stacks

The system uses a **two-stack deployment approach** to solve the "chicken and egg" problem where the frontend needs the API URL to build, but the API URL isn't known until deployment:

1. **ApiStack**: Deploys the backend API infrastructure first
   - API Gateway with Lambda proxy integration
   - Workflows API Lambda function
   - IAM roles and permissions
   - Exports the API Gateway URL for the frontend stack

2. **FrontendStack**: Deploys the frontend with automatic API configuration
   - Builds the React application with a placeholder API URL
   - Deploys static assets to S3 with website hosting
   - Injects the real API URL via runtime configuration (config.js)
   - Depends on ApiStack to ensure proper deployment order

### Key Features

- **Automated Deployment**: No manual .env file editing required
- **Runtime Configuration**: Frontend automatically discovers API URL at runtime
- **Web Dashboard**: Visual workflow management with DAG visualization
- **Real-time Status**: Live workflow status updates
- **Idempotency**: Version-based optimistic locking prevents duplicate executions
- **Concurrency Control**: Multiple workers can safely process tasks simultaneously
- **Event-Driven**: Uses DynamoDB Streams for reactive coordination

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

### 4. Install Node.js and npm

```bash
# On macOS
brew install node

# On Linux
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# On Windows
# Download and install from https://nodejs.org/
```

### 5. Install UV (Python Package Manager)

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

# Create Python virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### 2. Install Frontend Dependencies

```bash
cd web/workflow-dashboard
npm install
cd ../..
```

### 3. Bootstrap CDK (First Time Only)

```bash
# Bootstrap CDK in your AWS account/region
uv run cdk bootstrap
```

### 4. Deploy Infrastructure

The deployment uses a two-stack approach for optimal automation:

```bash
# Deploy the API stack first (backend infrastructure)
uv run cdk deploy ApiStack

# Deploy the frontend stack second (automatically configured with API URL)
uv run cdk deploy FrontendStack

# Or deploy both stacks at once (CDK handles dependencies)
uv run cdk deploy --all
```

The deployment process:
1. **ApiStack** deploys the backend API and exports the API Gateway URL
2. **FrontendStack** automatically builds the React app and injects the correct API URL
3. No manual configuration or .env file editing required

### 5. Access the Application

After deployment, the CDK outputs will show:
- **API Gateway URL**: For direct API access
- **Frontend Dashboard URL**: For the web interface (S3 website hosting)

Example output:
```
Outputs:
ApiStack.WorkflowsApiEndpoint = https://abc123.execute-api.eu-central-1.amazonaws.com/prod/
FrontendStack.DashboardUrl = http://frontendstack-bucket.s3-website.eu-central-1.amazonaws.com
```

## Usage

### Web Dashboard (Recommended)

After deployment, access the workflow dashboard via the S3 website URL from the CDK outputs:

1. **Frontend URL**: Use the FrontendStack DashboardUrl from CDK outputs
2. **Automatic Configuration**: The frontend automatically loads the correct API URL at runtime

The dashboard provides:
- **Workflow List**: View all workflows and their current status
- **Workflow Details**: Visual DAG representation of task dependencies
- **Real-time Updates**: Live status updates as workflows execute
- **Workflow Creation**: Start new workflows with auto-generated IDs

### API Endpoints

The REST API provides the following endpoints:

```bash
# List all workflows
GET /workflows

# Get specific workflow details
GET /workflows/{workflowId}

```bash
# Create a new workflow (API will auto-generate workflow ID and start execution)
POST /workflows
{
  "workflowId": "my-workflow-123"
}
```

**Note**: The `lambdas` parameter is no longer required as the orchestrator now has access to the Lambda ARNs via environment variables.
```

### CLI Tool (For Testing)

Use the provided test script to execute workflows programmatically:

```bash
# Run with the orchestrator ARN from CDK outputs
uv run python tools/invoke_all.py \
  --orchestrator-arn <orchestrator-arn-from-cdk-output> \
  --region eu-central-1 \
  --stack-name OrchestrationStack
```

### Development Mode

#### Frontend Development

For frontend development with hot reload:

```bash
cd web/workflow-dashboard

# The API URL is automatically loaded at runtime via config.js
# No environment variable configuration needed

# Start development server
npm run dev

# The dashboard will be available at http://localhost:5173
```

#### Backend Development

For backend API development:

```bash
# Deploy only the API stack changes
uv run cdk deploy ApiStack

# Deploy only the orchestration changes
uv run cdk deploy OrchestrationStack

# Monitor logs
aws logs tail /aws/lambda/workflow-api --follow
```

### Production Deployment

#### Building and Deploying

```bash
# The build process is fully automated
# Just deploy the stacks and everything is handled automatically

cd /path/to/orchestra

# Deploy both stacks (or individually as needed)
uv run cdk deploy --all
```

The deployment process automatically:
1. **ApiStack**: Deploys backend infrastructure and exports API URL
2. **FrontendStack**: Builds React app, uploads to S3, and injects runtime configuration
3. **No manual steps**: Everything is automated including API URL configuration

### Monitoring Workflows

1. **Web Dashboard**: Real-time workflow status and visual DAG representation
2. **DynamoDB Console**: View raw workflow state and task progress
3. **CloudWatch Logs**: Monitor Lambda execution logs
4. **API Gateway Console**: Track API request metrics

## Project Structure

```
orchestra/
├── src/
│   ├── api/
│   │   └── workflows_api.py          # REST API for workflow management
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
│       ├── api_stack.py              # API infrastructure (API Gateway, Lambda)
│       ├── frontend_stack.py         # Frontend deployment (S3, build automation)
│       ├── orchestration_stack.py    # Lambda orchestration resources
│       ├── payload_stack.py          # Shared resources (DynamoDB, ECR)
│       └── monitoring_stack.py       # Monitoring resources
├── web/
│   └── workflow-dashboard/           # React frontend
│       ├── src/
│       │   ├── components/
│       │   │   ├── WorkflowGraph.tsx # DAG visualization
│       │   │   └── WorkflowList.tsx  # Workflow list view
│       │   ├── services/
│       │   │   └── api.ts            # API client
│       │   └── App.tsx               # Main React app
│       ├── public/
│       │   └── config.js             # Runtime configuration template
│       ├── package.json
│       └── vite.config.ts
├── tools/
│   └── invoke_all.py                 # CLI tool for testing
├── tests/
│   └── unit/                         # Unit tests
├── pyproject.toml
├── uv.lock
└── README.md
```

## How It Works

### Two-Stack Deployment Architecture

The system solves the "chicken and egg" problem where the frontend needs the API URL to build, but the API URL isn't available until after deployment:

1. **ApiStack Deployment**: 
   - Deploys API Gateway and Lambda functions
   - Exports the API Gateway URL for other stacks to reference
   - Sets up CORS configuration for frontend access

2. **FrontendStack Deployment**:
   - Depends on ApiStack (automatic dependency resolution by CDK)
   - Builds React application with placeholder API URL
   - Deploys static assets to S3 with website hosting
   - Injects real API URL via runtime configuration file (config.js)
   - Frontend loads API URL at runtime, not build time

### Event-Driven Orchestration

1. **API Request**: User creates workflow via web dashboard or API
2. **Initialization**: Orchestrator seeds workflow graph in DynamoDB
3. **Task Execution**: Worker Lambda executes tasks with version-based locking
4. **Dependency Resolution**: DynamoDB Streams trigger fan-out when tasks complete
5. **State Management**: Conditional updates ensure exactly-once execution
6. **Real-time Updates**: API provides current status for dashboard display

### Workflow States

- **PENDING**: Workflow created, waiting to start
- **RUNNING**: Workflow executing with active tasks
- **SUCCESS**: All tasks completed successfully
- **FAILED**: One or more tasks failed

### Task States

- **PENDING**: Task waiting for dependencies
- **READY**: Task ready for execution
- **RUNNING**: Task currently executing
- **SUCCEEDED**: Task completed successfully
- **FAILED**: Task execution failed

### Key Concepts

- **Version Control**: Optimistic locking prevents race conditions
- **Idempotency**: Tasks execute exactly once even with retries
- **Fan-out**: Orchestrator triggers dependent tasks when dependencies complete
- **DAG Visualization**: Frontend renders task dependencies as directed acyclic graph

## Task Implementation Examples

The project includes sample tasks implemented in different runtimes:

- **Lambda A** (Node.js): Simple function that returns workflow metadata
- **Lambda B1** (Node.js): Processes data and returns results
- **Lambda B2** (Python): Demonstrates Python-based task execution
- **Lambda B3** (Container): Shows containerized Lambda deployment
- **Lambda C** (Node.js): Final aggregation task

## Development Commands

### Backend Development

```bash
# Install Python dependencies
uv pip install -r requirements.txt

# Run type checking
uv run mypy src/

# Run tests
uv run pytest

# Format code
uv run black src/ tools/
uv run isort src/ tools/

# Deploy API infrastructure
uv run cdk deploy ApiStack

# Deploy frontend infrastructure
uv run cdk deploy FrontendStack

# Deploy all stacks
uv run cdk deploy --all

# Destroy infrastructure
uv run cdk destroy --all

# View CDK diff
uv run cdk diff

# Synthesize CloudFormation
uv run cdk synth
```

### Frontend Development

```bash
cd web/workflow-dashboard

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Run type checking
npm run type-check

# Run linting
npm run lint

# Run tests
npm test
```

### Full Stack Development

```bash
# 1. Deploy backend infrastructure first
uv run cdk deploy ApiStack

# 2. Deploy frontend (automatically gets API URL from ApiStack)
uv run cdk deploy FrontendStack

# 3. Get frontend URL from CDK outputs and access dashboard
# No environment variable configuration needed - everything is automatic

# 4. For local development with hot reload:
cd web/workflow-dashboard
npm run dev

# 5. Access local dashboard at http://localhost:5173
# Local dashboard will use the deployed API from step 1
```

## Configuration

### Environment Variables

The system uses the following environment variables:

#### Backend (Lambda)
- `TABLE_NAME`: DynamoDB table name (set by CDK)
- `WORKER_ARN`: Worker Lambda ARN (set by CDK)
- `ORCHESTRATOR_ARN`: Orchestrator Lambda ARN (set by CDK)

#### Frontend (React)
- **Runtime Configuration**: API URL loaded from `/config.js` at runtime
- `VITE_API_BASE`: Fallback API URL for development (optional)

#### Development
- `AWS_REGION`: AWS region for deployment
- `CDK_DEFAULT_REGION`: Default region for CDK

### CDK Context

The CDK application can be configured via `cdk.json`:

```json
{
  "app": "uv run python src/app.py",
  "context": {
    "@aws-cdk/core:enableStackNameDuplicates": true,
    "aws-cdk:enableDiffNoFail": true
  }
}
```

## Troubleshooting

### Common Issues

1. **Frontend Not Loading API Configuration**: 
   ```bash
   # Check that config.js is properly deployed
   curl http://your-frontend-url.s3-website.region.amazonaws.com/config.js
   
   # Should return: window.API_BASE = 'https://your-api-url.amazonaws.com/prod';
   ```

2. **CORS Errors in Frontend**: 
   ```bash
   # Verify API Gateway CORS configuration in AWS console
   # Check that frontend domain is allowed in CORS settings
   ```

2. **Frontend Build Issues**:
   ```bash
   cd web/workflow-dashboard
   
   # Clear cache and reinstall
   rm -rf node_modules package-lock.json
   npm install
   
   # Check Node.js version (requires Node 16+)
   node --version
   
   # Manual build test
   npm run build
   ```

3. **Stack Deployment Order Issues**:
   ```bash
   # If FrontendStack fails due to missing API URL:
   uv run cdk deploy ApiStack
   uv run cdk deploy FrontendStack
   
   # Or use --all flag for automatic dependency resolution
   uv run cdk deploy --all
   ```

4. **Lambda Import Errors**: Ensure absolute imports in Lambda functions
   ```python
   # Good
   from ddb_workflow.workflow_types import TaskExecutionRequest
   
   # Bad
   from .workflow_types import TaskExecutionRequest
   ```

5. **Permission Errors**: Verify IAM roles have necessary permissions
   - DynamoDB read/write access
   - Lambda invoke permissions
   - CloudWatch Logs access
   - S3 read access for static hosting

6. **API Gateway 502 Errors**: Check Lambda function logs
   ```bash
   aws logs tail /aws/lambda/workflow-api --follow
   ```

7. **S3 Website Access Issues**: 
   ```bash
   # Check S3 bucket website configuration
   aws s3api get-bucket-website --bucket your-frontend-bucket-name
   
   # Verify bucket policy allows public read access for website hosting
   ```

### Debugging Tips

1. **Frontend Issues**: 
   ```bash
   # Check browser console for errors
   # Inspect Network tab for API calls
   # Verify config.js loads correctly: /config.js endpoint
   ```

2. **Backend API Issues**:
   ```bash
   # Check CloudWatch Logs for API Lambda
   aws logs tail /aws/lambda/workflow-api --follow
   
   # Test API endpoints directly
   curl -X GET https://your-api-id.execute-api.region.amazonaws.com/workflows
   ```

3. **CloudWatch Logs**: Check logs for detailed error messages
   ```bash
   aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/"
   ```

4. **DynamoDB Console**: Inspect workflow state and task progress

5. **X-Ray Tracing**: Enable for distributed tracing (optional)

### Performance Tuning

- **Lambda Memory**: Adjust based on task requirements
- **DynamoDB Capacity**: Configure read/write capacity units
- **Timeout Settings**: Set appropriate timeouts for tasks
- **CloudFront Caching**: Configure optimal cache settings for static assets
- **API Gateway Caching**: Enable caching for frequently accessed endpoints

## Testing

### Unit Tests

```bash
# Run Python unit tests
uv run pytest tests/unit/

# Run with coverage
uv run pytest --cov=src tests/

# Run specific test file
uv run pytest tests/unit/test_orchestrator_lambda.py -v
```

### Frontend Tests

```bash
cd web/workflow-dashboard

# Run React component tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run tests with coverage
npm test -- --coverage
```

### Integration Tests

```bash
# Deploy test stacks
uv run cdk deploy --all

# Test via web dashboard
# Open the S3 website URL and create a test workflow

# Test via API (get URL from ApiStack outputs)
curl -X POST https://your-api-id.execute-api.region.amazonaws.com/prod/workflows \
  -H "Content-Type: application/json" \
  -d '{"workflowId": "test-workflow-123"}'

# Check DynamoDB for workflow completion
aws dynamodb scan --table-name YourTableName --region your-region
```

### End-to-End Testing

```bash
# 1. Deploy both stacks
uv run cdk deploy --all

# 2. Get the frontend URL from FrontendStack outputs
# 3. Open the dashboard in browser
# 4. Create a workflow and verify:
#    - Workflow appears in list
#    - Tasks execute in correct order
#    - Status updates in real-time
#    - DAG visualization shows progress
```

## Monitoring and Observability

### CloudWatch Metrics

The system exports custom metrics:
- Workflow execution duration
- Task success/failure rates
- Concurrent executions
- API Gateway request metrics
- CloudFront cache hit rates

### Alarms

Set up CloudWatch alarms for:
- Lambda errors and timeouts
- DynamoDB throttling
- API Gateway 4xx/5xx errors
- Workflow failures

### Dashboards

Create CloudWatch dashboards to monitor:
- Workflow throughput and completion rates
- Task execution times
- API performance metrics
- System health and error rates
- Frontend performance (CloudFront metrics)

## Security Considerations

- **IAM Roles**: Follow principle of least privilege
- **CORS Configuration**: Properly configured for frontend domain
- **API Gateway**: Enable request validation and throttling
- **S3 Website Hosting**: Configured for public read access with website hosting
- **Static Assets**: Secure deployment of frontend assets
- **Runtime Configuration**: Secure injection of API URLs without exposing secrets
- **Encryption**: Enable encryption at rest for DynamoDB and S3
- **Secrets**: Use AWS Secrets Manager for sensitive data

## Cost Optimization

- **Reserved Capacity**: Use for predictable DynamoDB workloads
- **Lambda Provisioned Concurrency**: For consistent performance
- **CloudWatch Log Retention**: Set appropriate retention periods
- **S3 Storage Classes**: Use appropriate storage class for static assets
- **API Gateway Caching**: Enable caching to reduce Lambda invocations
- **Resource Cleanup**: Destroy unused stacks and clear old CloudWatch logs

## Cleanup

To avoid AWS charges, destroy the infrastructure when done:

```bash
uv run cdk destroy --all
```

Verify all resources are deleted:
```bash
aws cloudformation list-stacks --stack-status-filter DELETE_COMPLETE
```

Note: S3 buckets with content may need manual cleanup before stack deletion.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines for Python code
- Use TypeScript for frontend development
- Add type hints for all Python functions
- Include docstrings for public methods
- Write tests for new functionality
- Update documentation as needed
- Follow React best practices for component development
- Use proper error handling and user feedback in the UI

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
