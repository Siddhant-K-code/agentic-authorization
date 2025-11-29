"""
Data models for the authorization system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class AuditEvent:
    """Represents an audit event for compliance and security tracking."""
    timestamp: datetime
    event_type: str  # "delegation_created", "access_checked", "access_denied", "task_revoked"
    user_id: str
    agent_id: str
    task_id: str
    resource_id: Optional[str] = None
    decision: str = "allowed"  # "allowed", "denied"
    reason: str = ""
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TaskMetadata:
    """Metadata for a task delegation."""
    task_id: str
    user_id: str
    agent_id: str
    description: str
    expires_at: datetime
    created_at: datetime
    status: str = "active"  # "active", "revoked", "expired"
    resources: list = None

    def __post_init__(self):
        if self.resources is None:
            self.resources = []

