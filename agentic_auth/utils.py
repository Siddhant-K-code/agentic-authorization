"""
Utility functions for the authorization system.
"""

import asyncio
from datetime import datetime
from typing import List

from .auth_service import AgentAuthorizationService
from .models import AuditEvent


async def cleanup_expired_tasks(
    auth_service: AgentAuthorizationService,
    logger=None
) -> int:
    """
    Background job to revoke expired tasks.

    Run this periodically (e.g., every minute) via a scheduler.

    Args:
        auth_service: The authorization service to use
        logger: Optional logger instance

    Returns:
        Number of tasks revoked
    """
    expired_tasks = await auth_service.get_expired_task_ids()
    revoked_count = 0

    for task_id in expired_tasks:
        try:
            await auth_service.revoke_task(task_id)
            revoked_count += 1
            if logger:
                logger.info(f"Revoked expired task: {task_id}")
        except Exception as e:
            if logger:
                logger.error(f"Failed to revoke task {task_id}: {e}")

    return revoked_count


async def log_audit_event(
    event: AuditEvent,
    audit_store: List[AuditEvent]
):
    """
    Log an audit event to the audit store.

    In production, this would write to your audit system of choice
    (e.g., a database, logging service, or compliance system).

    Args:
        event: The audit event to log
        audit_store: List to append the event to
    """
    audit_store.append(event)


async def initiate_agent_task(
    user_id: str,
    agent_id: str,
    user_request: str,
    auth_service: AgentAuthorizationService,
    scope_service,
    get_user_resources_func
) -> dict:
    """
    Complete flow: user request → scope inference → task creation → agent execution.

    This is the main entry point for initiating an agent task with proper
    authorization scoping.

    Args:
        user_id: ID of the user initiating the task
        agent_id: ID of the agent to execute the task
        user_request: Natural language description of what the user wants
        auth_service: Authorization service instance
        scope_service: ScopeInferenceService instance
        get_user_resources_func: Async function that returns user's available resources

    Returns:
        Dictionary with task context:
        {
            "task_id": str,
            "scopes": dict,
            "agent_id": str,
            "status": str
        }
    """
    # 1. Get user's available resources
    user_resources = await get_user_resources_func(user_id)

    # 2. Infer minimal required scopes
    inferred_scopes = await scope_service.infer_scopes(
        user_request=user_request,
        available_resources=user_resources
    )

    # 3. Create task with scoped permissions
    task_id = await auth_service.create_task_delegation(
        user_id=user_id,
        agent_id=agent_id,
        task_description=user_request,
        allowed_resources=inferred_scopes["resources"],
        ttl_minutes=30
    )

    # 4. Return task context for agent execution
    return {
        "task_id": task_id,
        "scopes": inferred_scopes,
        "agent_id": agent_id,
        "status": "ready"
    }

