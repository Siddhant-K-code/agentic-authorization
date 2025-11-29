"""
Example usage of the agentic authorization system.

This demonstrates the complete flow from user request to authorized agent execution.
"""

import asyncio
import os
from openfga_sdk import OpenFgaClient, ClientConfiguration
from anthropic import Anthropic

from agentic_auth import (
    AgentAuthorizationService,
    AuthorizationGateway,
    ScopeInferenceService,
    CachedAuthorizationService
)
from agentic_auth.utils import initiate_agent_task


async def example_complete_flow():
    """
    Example of the complete authorization flow.

    This shows:
    1. Setting up OpenFGA and Anthropic clients
    2. Creating authorization services
    3. Initiating a task with scope inference
    4. Using authorized tools
    """
    # Configuration
    OPENFGA_API_URL = os.getenv("OPENFGA_API_URL", "http://localhost:8080")
    OPENFGA_STORE_ID = os.getenv("OPENFGA_STORE_ID", "your-store-id")
    OPENFGA_CLIENT_ID = os.getenv("OPENFGA_CLIENT_ID", "")
    OPENFGA_CLIENT_SECRET = os.getenv("OPENFGA_CLIENT_SECRET", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Initialize OpenFGA client
    configuration = ClientConfiguration(
        api_url=OPENFGA_API_URL,
        store_id=OPENFGA_STORE_ID,
    )

    if OPENFGA_CLIENT_ID and OPENFGA_CLIENT_SECRET:
        configuration.credentials = {
            "client_id": OPENFGA_CLIENT_ID,
            "client_secret": OPENFGA_CLIENT_SECRET,
        }

    openfga_client = OpenFgaClient(configuration)

    # Initialize Anthropic client for scope inference
    anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Create authorization service (with caching for performance)
    auth_service = CachedAuthorizationService(
        openfga_client=openfga_client,
        store_id=OPENFGA_STORE_ID,
        cache_ttl_seconds=60
    )

    # Create scope inference service
    scope_service = ScopeInferenceService(
        anthropic_client=anthropic_client
    )

    # Create authorization gateway
    gateway = AuthorizationGateway(auth_service=auth_service)

    # Example: User initiates a task
    user_id = "alice"
    agent_id = "agent-123"
    user_request = "Summarize emails from last week and post the summary to the team Slack channel"

    # Mock function to get user's available resources
    async def get_user_resources(user_id: str):
        """In production, this would query your resource management system."""
        return [
            {"type": "email", "id": "gmail:alice@example.com", "access": "read"},
            {"type": "slack", "id": "slack:channel-team", "access": "write"},
        ]

    # Initiate the task with scope inference
    task_context = await initiate_agent_task(
        user_id=user_id,
        agent_id=agent_id,
        user_request=user_request,
        auth_service=auth_service,
        scope_service=scope_service,
        get_user_resources_func=get_user_resources
    )

    print(f"Task created: {task_context['task_id']}")
    print(f"Inferred scopes: {task_context['scopes']}")

    # Now the agent can use authorized tools
    # Example: Reading a document (would be called by the agent)
    try:
        from examples.example_tools import example_read_document

        result = await example_read_document(
            gateway=gateway,
            document_id="doc-123",
            agent_id=agent_id,
            task_id=task_context["task_id"]
        )
        print(f"Document read successfully: {result[:50]}...")
    except Exception as e:
        print(f"Authorization failed: {e}")

    # Example: Revoking a task
    revocation_result = await auth_service.revoke_task(task_context["task_id"])
    print(f"Task revoked: {revocation_result}")


async def example_manual_delegation():
    """
    Example of manually creating a task delegation without scope inference.

    Useful when you know exactly which resources the agent needs.
    """
    # Setup (same as above)
    OPENFGA_API_URL = os.getenv("OPENFGA_API_URL", "http://localhost:8080")
    OPENFGA_STORE_ID = os.getenv("OPENFGA_STORE_ID", "your-store-id")

    configuration = ClientConfiguration(
        api_url=OPENFGA_API_URL,
        store_id=OPENFGA_STORE_ID,
    )
    openfga_client = OpenFgaClient(configuration)

    auth_service = AgentAuthorizationService(
        openfga_client=openfga_client,
        store_id=OPENFGA_STORE_ID
    )

    # Manually specify resources
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

    print(f"Task created: {task_id}")

    # Check authorization
    authorized, reason = await auth_service.check_agent_resource_access(
        agent_id="agent-123",
        task_id=task_id,
        resource_id="resource:doc-123",
        access_type="reader"
    )

    print(f"Authorization check: {authorized} - {reason}")


if __name__ == "__main__":
    # Run the example
    asyncio.run(example_complete_flow())

