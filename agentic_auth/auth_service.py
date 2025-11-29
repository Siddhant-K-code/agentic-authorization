"""
Core authorization service for agent task delegation and access control.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from openfga_sdk import OpenFgaClient, ClientConfiguration
from openfga_sdk.models import ClientTuple

from .models import TaskMetadata, AuditEvent


class AgentAuthorizationService:
    """
    Service for managing agent authorization using Relationship-Based Access Control.

    This service handles:
    - Creating task-scoped delegations from users to agents
    - Checking agent access to resources within task contexts
    - Revoking tasks and their associated permissions
    """

    def __init__(
        self,
        openfga_client: OpenFgaClient,
        store_id: str,
        task_metadata_store: Optional[Any] = None,
        audit_store: Optional[Any] = None
    ):
        """
        Initialize the authorization service.

        Args:
            openfga_client: Configured OpenFGA client
            store_id: OpenFGA store ID
            task_metadata_store: Optional store for task metadata (dict-like interface)
            audit_store: Optional store for audit events (dict-like interface)
        """
        self.client = openfga_client
        self.store_id = store_id
        self.task_metadata_store = task_metadata_store or {}
        self.audit_store = audit_store or []

    async def create_task_delegation(
        self,
        user_id: str,
        agent_id: str,
        task_description: str,
        allowed_resources: List[Dict[str, Any]],
        ttl_minutes: int = 30
    ) -> str:
        """
        Create a task-scoped delegation from user to agent.

        This establishes a permission boundary: the agent can only
        access resources explicitly linked to this task.

        Args:
            user_id: ID of the user delegating authority
            agent_id: ID of the agent receiving authority
            task_description: Human-readable description of the task
            allowed_resources: List of resources the task can access
                Each resource dict should have: {"id": str, "access": str}
            ttl_minutes: Time-to-live for the task in minutes

        Returns:
            task_id: The created task ID
        """
        task_id = f"task:{uuid.uuid4()}"
        expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)

        tuples = [
            # User delegates to this task
            ClientTuple(
                user=f"user:{user_id}",
                relation="delegator",
                object=task_id
            ),
            # Agent is assigned to this task
            ClientTuple(
                user=f"agent:{agent_id}",
                relation="assignee",
                object=task_id
            ),
        ]

        # Scope specific resources to this task
        for resource in allowed_resources:
            resource_id = resource["id"]
            access_level = resource.get("access", "reader")

            tuples.append(
                ClientTuple(
                    user=task_id,
                    relation=access_level,
                    object=f"resource:{resource_id}"
                )
            )

        # Write all tuples to OpenFGA
        await self.client.write(
            body={"writes": {"tuple_keys": tuples}},
            options={"store_id": self.store_id}
        )

        # Store task metadata (for expiration handling)
        await self._store_task_metadata(task_id, {
            "user_id": user_id,
            "agent_id": agent_id,
            "description": task_description,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "resources": allowed_resources
        })

        # Log audit event
        await self._log_audit_event(AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="delegation_created",
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            decision="allowed",
            reason="Task delegation created",
            metadata={
                "description": task_description,
                "ttl_minutes": ttl_minutes,
                "resource_count": len(allowed_resources)
            }
        ))

        return task_id

    async def check_agent_resource_access(
        self,
        agent_id: str,
        task_id: str,
        resource_id: str,
        access_type: str = "reader"
    ) -> Tuple[bool, str]:
        """
        Check if an agent can access a resource within a task context.

        Returns (authorized: bool, reason: str)

        Args:
            agent_id: ID of the agent requesting access
            task_id: ID of the task context
            resource_id: ID of the resource being accessed
            access_type: Required access level ("reader" or "writer")
        """
        # First: Is this agent assigned to this task?
        agent_assigned = await self.client.check(
            body={
                "tuple_key": {
                    "user": f"agent:{agent_id}",
                    "relation": "assignee",
                    "object": task_id
                }
            },
            options={"store_id": self.store_id}
        )

        if not agent_assigned.allowed:
            reason = "Agent not assigned to this task"
            await self._log_audit_event(AuditEvent(
                timestamp=datetime.utcnow(),
                event_type="access_denied",
                user_id="",  # Will be filled from task metadata if available
                agent_id=agent_id,
                task_id=task_id,
                resource_id=resource_id,
                decision="denied",
                reason=reason
            ))
            return False, reason

        # Second: Does this task have access to this resource?
        task_has_access = await self.client.check(
            body={
                "tuple_key": {
                    "user": task_id,
                    "relation": access_type,
                    "object": f"resource:{resource_id}"
                }
            },
            options={"store_id": self.store_id}
        )

        if not task_has_access.allowed:
            reason = f"Task does not have {access_type} access to resource"
            await self._log_audit_event(AuditEvent(
                timestamp=datetime.utcnow(),
                event_type="access_denied",
                user_id="",
                agent_id=agent_id,
                task_id=task_id,
                resource_id=resource_id,
                decision="denied",
                reason=reason
            ))
            return False, reason

        # Authorized
        await self._log_audit_event(AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="access_checked",
            user_id="",
            agent_id=agent_id,
            task_id=task_id,
            resource_id=resource_id,
            decision="allowed",
            reason="Authorized"
        ))

        return True, "Authorized"

    async def revoke_task(self, task_id: str) -> Dict[str, Any]:
        """
        Revoke a task and all its associated permissions.

        This is where ReBAC shines: deleting the task relationships
        cascades to remove all resource access.

        Args:
            task_id: ID of the task to revoke

        Returns:
            Dictionary with revocation details
        """
        # Read all tuples where this task is involved
        related_tuples = await self.client.read(
            body={"tuple_key": {"object": task_id}},
            options={"store_id": self.store_id}
        )

        # Also get tuples where task is the user (accessing resources)
        task_access_tuples = await self.client.read(
            body={"tuple_key": {"user": task_id}},
            options={"store_id": self.store_id}
        )

        all_tuples = []
        if hasattr(related_tuples, 'tuples'):
            all_tuples.extend(related_tuples.tuples)
        if hasattr(task_access_tuples, 'tuples'):
            all_tuples.extend(task_access_tuples.tuples)

        if all_tuples:
            await self.client.write(
                body={
                    "deletes": {
                        "tuple_keys": [
                            {
                                "user": t.key.user,
                                "relation": t.key.relation,
                                "object": t.key.object
                            }
                            for t in all_tuples
                        ]
                    }
                },
                options={"store_id": self.store_id}
            )

        # Get task metadata for audit logging
        task_metadata = await self._get_task_metadata(task_id)
        user_id = task_metadata.get("user_id", "") if task_metadata else ""
        agent_id = task_metadata.get("agent_id", "") if task_metadata else ""

        await self._delete_task_metadata(task_id)

        # Log audit event
        await self._log_audit_event(AuditEvent(
            timestamp=datetime.utcnow(),
            event_type="task_revoked",
            user_id=user_id,
            agent_id=agent_id,
            task_id=task_id,
            decision="revoked",
            reason="Task revoked",
            metadata={"tuples_revoked": len(all_tuples)}
        ))

        return {
            "task_id": task_id,
            "tuples_revoked": len(all_tuples),
            "status": "revoked"
        }

    async def get_expired_task_ids(self) -> List[str]:
        """
        Get list of task IDs that have expired.

        Returns:
            List of expired task IDs
        """
        expired_tasks = []
        now = datetime.utcnow()

        for task_id, metadata in self.task_metadata_store.items():
            if isinstance(metadata, dict):
                expires_at_str = metadata.get("expires_at")
                if expires_at_str:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                        if expires_at < now:
                            expired_tasks.append(task_id)
                    except (ValueError, AttributeError):
                        continue

        return expired_tasks

    async def _store_task_metadata(self, task_id: str, metadata: Dict[str, Any]):
        """Store task metadata."""
        self.task_metadata_store[task_id] = metadata

    async def _get_task_metadata(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve task metadata."""
        return self.task_metadata_store.get(task_id)

    async def _delete_task_metadata(self, task_id: str):
        """Delete task metadata."""
        if task_id in self.task_metadata_store:
            del self.task_metadata_store[task_id]

    async def _log_audit_event(self, event: AuditEvent):
        """Log an audit event."""
        self.audit_store.append(event)

