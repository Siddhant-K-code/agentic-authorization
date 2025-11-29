# Agentic Authorization

Authorization patterns for autonomous AI agent systems using Relationship-Based Access Control (ReBAC) with OpenFGA.

This project implements the authorization model described in the blog post "Securing Agentic AI: Authorization Patterns for Autonomous Systems", providing task-scoped delegation, authorization gateways, and scope inference for AI agents.

## Features

- **Task-Scoped Delegation**: Agents receive permissions scoped to specific tasks, not broad access
- **Relationship-Based Access Control**: Uses OpenFGA for graph-based authorization
- **Authorization Gateway**: Wraps all tool calls with authorization checks
- **Scope Inference**: Uses LLMs to infer minimal required permissions from natural language
- **Automatic Expiration**: Tasks expire automatically after TTL
- **Audit Logging**: Complete audit trail of all authorization decisions
- **Performance Caching**: Cached authorization checks for improved performance

## Installation

```bash
pip install -r requirements.txt
```

## Prerequisites

1. **OpenFGA**: You need a running OpenFGA instance. See [OpenFGA documentation](https://openfga.dev/docs) for setup instructions.

2. **Anthropic API Key**: For scope inference, you'll need an Anthropic API key.

3. **Environment Variables**:
   ```bash
   export OPENFGA_API_URL="http://localhost:8080"
   export OPENFGA_STORE_ID="your-store-id"
   export OPENFGA_CLIENT_ID="your-client-id"  # Optional, for auth
   export OPENFGA_CLIENT_SECRET="your-client-secret"  # Optional, for auth
   export ANTHROPIC_API_KEY="your-anthropic-api-key"
   ```

## Setup

### 1. Deploy the Authorization Model

First, deploy the OpenFGA authorization model to your OpenFGA instance:

```bash
# Using OpenFGA CLI (if installed)
openfga model write --store-id $OPENFGA_STORE_ID agentic_auth/model.fga

# Or use the OpenFGA API directly
curl -X POST "$OPENFGA_API_URL/stores/$OPENFGA_STORE_ID/authorization-models" \
  -H "Content-Type: application/json" \
  -d @agentic_auth/model.fga
```

### 2. Initialize Resources

Before agents can access resources, you need to create resource tuples in OpenFGA:

```python
from openfga_sdk import OpenFgaClient, ClientConfiguration
from openfga_sdk.models import ClientTuple

# Setup client
config = ClientConfiguration(
    api_url="http://localhost:8080",
    store_id="your-store-id"
)
client = OpenFgaClient(config)

# Create a resource owned by a user
await client.write(
    body={
        "writes": {
            "tuple_keys": [
                ClientTuple(
                    user="user:alice",
                    relation="owner",
                    object="resource:doc-123"
                )
            ]
        }
    },
    options={"store_id": "your-store-id"}
)
```

## Usage

### Basic Example

```python
import asyncio
from openfga_sdk import OpenFgaClient, ClientConfiguration
from anthropic import Anthropic
from agentic_auth import (
    AgentAuthorizationService,
    AuthorizationGateway,
    ScopeInferenceService
)
from agentic_auth.utils import initiate_agent_task

async def main():
    # Initialize clients
    openfga_client = OpenFgaClient(
        ClientConfiguration(
            api_url="http://localhost:8080",
            store_id="your-store-id"
        )
    )
    anthropic_client = Anthropic(api_key="your-api-key")

    # Create services
    auth_service = AgentAuthorizationService(
        openfga_client=openfga_client,
        store_id="your-store-id"
    )
    scope_service = ScopeInferenceService(anthropic_client)
    gateway = AuthorizationGateway(auth_service)

    # Initiate a task
    async def get_user_resources(user_id: str):
        return [
            {"type": "email", "id": "gmail:user@example.com", "access": "read"},
            {"type": "slack", "id": "slack:channel-team", "access": "write"},
        ]

    task_context = await initiate_agent_task(
        user_id="alice",
        agent_id="agent-123",
        user_request="Summarize emails from last week",
        auth_service=auth_service,
        scope_service=scope_service,
        get_user_resources_func=get_user_resources
    )

    print(f"Task ID: {task_context['task_id']}")

asyncio.run(main())
```

### Using Authorized Tools

```python
from agentic_auth.gateway import AuthorizationGateway

gateway = AuthorizationGateway(auth_service)

@gateway.authorized_tool(
    resource_extractor=lambda args: args["document_id"],
    access_type="reader"
)
async def read_document(document_id: str) -> str:
    """Read a document from the document store."""
    return await document_store.get(document_id)

# The agent calls it with task context
result = await read_document(
    agent_id="agent-123",
    task_id="task:abc-123",
    document_id="doc-123"
)
```

### Manual Task Delegation

If you know exactly which resources are needed, you can skip scope inference:

```python
task_id = await auth_service.create_task_delegation(
    user_id="alice",
    agent_id="agent-123",
    task_description="Read project documents",
    allowed_resources=[
        {"id": "resource:doc-123", "access": "reader"},
        {"id": "resource:doc-456", "access": "reader"},
    ],
    ttl_minutes=30
)
```

### Revoking Tasks

```python
# Revoke a specific task
result = await auth_service.revoke_task("task:abc-123")

# Or set up automatic cleanup of expired tasks
from agentic_auth.utils import cleanup_expired_tasks

# Run this periodically (e.g., every minute)
await cleanup_expired_tasks(auth_service)
```

## Architecture

### Authorization Model

The system uses a graph-based authorization model with the following entity types:

- **user**: The human delegating authority
- **agent**: The AI agent receiving authority
- **task**: The unit of delegation, connecting users, agents, and resources
- **resource**: External resources (documents, APIs, etc.)
- **tool**: Tools that agents can invoke

### Flow

1. **User Request**: User provides a natural language task description
2. **Scope Inference**: LLM analyzes the request and infers minimal required resources
3. **Task Creation**: A task is created with scoped permissions
4. **Agent Execution**: Agent invokes tools, each checked against task permissions
5. **Automatic Expiration**: Tasks expire after TTL or can be manually revoked

## Project Structure

```
agentic-authorization/
├── agentic_auth/
│   ├── __init__.py          # Package exports
│   ├── model.fga            # OpenFGA authorization model
│   ├── models.py            # Data models (AuditEvent, TaskMetadata)
│   ├── auth_service.py      # Core authorization service
│   ├── gateway.py           # Authorization gateway for tool wrapping
│   ├── scope_inference.py   # LLM-based scope inference
│   ├── caching.py           # Cached authorization service
│   └── utils.py             # Utility functions
├── examples/
│   ├── example_tools.py     # Example tool implementations
│   └── example_usage.py      # Complete usage examples
├── requirements.txt         # Python dependencies
├── pyproject.toml          # Project configuration
└── README.md               # This file
```

## Production Considerations

### Performance

- Use `CachedAuthorizationService` for better performance
- Cache TTL can be tuned based on your needs
- Denials are cached for shorter duration (10 seconds by default)

### Audit Logging

All authorization decisions are logged. In production, you should:

- Store audit logs in a persistent database
- Set up log retention policies
- Enable log analysis and alerting

### Task Expiration

Set up a background job to clean up expired tasks:

```python
import asyncio
from agentic_auth.utils import cleanup_expired_tasks

async def periodic_cleanup():
    while True:
        await cleanup_expired_tasks(auth_service)
        await asyncio.sleep(60)  # Run every minute

asyncio.create_task(periodic_cleanup())
```

### Error Handling

The `AuthorizationError` exception is raised when authorization fails. Handle it appropriately:

```python
from agentic_auth.gateway import AuthorizationError

try:
    result = await read_document(agent_id, task_id, document_id)
except AuthorizationError as e:
    # Log the denial
    logger.warning(f"Authorization denied: {e.audit_entry}")
    # Return appropriate error to agent
    return {"error": "Unauthorized access"}
```

## License

This project is provided as-is for educational and reference purposes.

## References

- [OpenFGA Documentation](https://openfga.dev/docs)
- [Relationship-Based Access Control](https://openfga.dev/docs/concepts#what-is-relationship-based-access-control-rebac)
- Blog post: "Securing Agentic AI: Authorization Patterns for Autonomous Systems"
