"""
Example tool implementations showing how to use the authorization gateway.
"""

from typing import Dict, Any
from agentic_auth.gateway import AuthorizationGateway, AuthorizationError


# Example document store (in production, this would be a real database/service)
class DocumentStore:
    """Mock document store for demonstration."""

    def __init__(self):
        self.documents = {
            "doc-123": "This is document 123 content...",
            "doc-456": "This is document 456 content...",
        }

    async def get(self, document_id: str) -> str:
        """Get a document by ID."""
        return self.documents.get(document_id, "")

    async def update(self, document_id: str, content: str) -> bool:
        """Update a document."""
        if document_id in self.documents:
            self.documents[document_id] = content
            return True
        return False


# Example Slack client (in production, this would be the real Slack API)
class SlackClient:
    """Mock Slack client for demonstration."""

    async def post_message(self, channel_id: str, message: str) -> bool:
        """Post a message to a Slack channel."""
        print(f"[Slack] Posting to channel {channel_id}: {message}")
        return True


# Initialize mock services
document_store = DocumentStore()
slack_client = SlackClient()


# Example: Setting up the authorization gateway
# (In production, you'd initialize this with your actual auth_service)
# gateway = AuthorizationGateway(auth_service)


# Example tool implementations with authorization
async def example_read_document(
    gateway: AuthorizationGateway,
    document_id: str,
    agent_id: str,
    task_id: str
) -> str:
    """
    Example of a read document tool with authorization.

    In production, you'd use the decorator like this:

    @gateway.authorized_tool(
        resource_extractor=lambda args: args["document_id"],
        access_type="reader"
    )
    async def read_document(document_id: str) -> str:
        return await document_store.get(document_id)
    """
    @gateway.authorized_tool(
        resource_extractor=lambda args: args["document_id"],
        access_type="reader"
    )
    async def read_document(document_id: str) -> str:
        """Read a document from the document store."""
        return await document_store.get(document_id)

    return await read_document(
        agent_id=agent_id,
        task_id=task_id,
        document_id=document_id
    )


async def example_update_document(
    gateway: AuthorizationGateway,
    document_id: str,
    content: str,
    agent_id: str,
    task_id: str
) -> bool:
    """
    Example of an update document tool with authorization.
    """
    @gateway.authorized_tool(
        resource_extractor=lambda args: args["document_id"],
        access_type="writer"
    )
    async def update_document(document_id: str, content: str) -> bool:
        """Update a document in the document store."""
        return await document_store.update(document_id, content)

    return await update_document(
        agent_id=agent_id,
        task_id=task_id,
        document_id=document_id,
        content=content
    )


async def example_post_to_slack(
    gateway: AuthorizationGateway,
    channel_id: str,
    message: str,
    agent_id: str,
    task_id: str
) -> bool:
    """
    Example of a Slack posting tool with authorization.
    """
    @gateway.authorized_tool(
        resource_extractor=lambda args: f"slack:{args['channel_id']}",
        access_type="writer"
    )
    async def post_to_slack(channel_id: str, message: str) -> bool:
        """Post a message to a Slack channel."""
        return await slack_client.post_message(channel_id, message)

    return await post_to_slack(
        agent_id=agent_id,
        task_id=task_id,
        channel_id=channel_id,
        message=message
    )

