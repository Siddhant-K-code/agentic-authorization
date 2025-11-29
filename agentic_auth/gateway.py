"""
Authorization gateway that wraps agent tool calls with authorization checks.
"""

from typing import Callable, Any, Dict
from functools import wraps
from datetime import datetime

from .auth_service import AgentAuthorizationService
from .models import AuditEvent


class AuthorizationError(Exception):
    """Raised when an authorization check fails."""

    def __init__(self, message: str, audit_entry: Dict[str, Any]):
        super().__init__(message)
        self.audit_entry = audit_entry


class AuthorizationGateway:
    """
    Gateway that wraps all agent tool calls with authorization checks.

    This ensures that every tool invocation is authorized before execution,
    providing a security boundary between agents and external resources.
    """

    def __init__(self, auth_service: AgentAuthorizationService):
        """
        Initialize the authorization gateway.

        Args:
            auth_service: The authorization service to use for checks
        """
        self.auth_service = auth_service
        self.audit_log = []

    def authorized_tool(
        self,
        resource_extractor: Callable[[Dict[str, Any]], str],
        access_type: str = "reader"
    ):
        """
        Decorator that wraps a tool function with authorization.

        Args:
            resource_extractor: Function to extract resource ID from tool args
            access_type: Required access level (reader, writer)

        Example:
            @gateway.authorized_tool(
                resource_extractor=lambda args: args["document_id"],
                access_type="reader"
            )
            async def read_document(document_id: str) -> str:
                return await document_store.get(document_id)
        """
        def decorator(tool_func: Callable):
            @wraps(tool_func)
            async def wrapper(
                agent_id: str,
                task_id: str,
                **kwargs
            ) -> Any:
                resource_id = resource_extractor(kwargs)

                # Check authorization
                authorized, reason = await self.auth_service.check_agent_resource_access(
                    agent_id=agent_id,
                    task_id=task_id,
                    resource_id=resource_id,
                    access_type=access_type
                )

                # Audit logging (always, regardless of outcome)
                audit_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "tool": tool_func.__name__,
                    "resource_id": resource_id,
                    "access_type": access_type,
                    "authorized": authorized,
                    "reason": reason
                }
                self.audit_log.append(audit_entry)

                if not authorized:
                    raise AuthorizationError(
                        f"Unauthorized: {reason}",
                        audit_entry=audit_entry
                    )

                # Execute the actual tool
                return await tool_func(**kwargs)

            return wrapper
        return decorator

