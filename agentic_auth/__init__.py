"""
Agentic Authorization - Relationship-Based Access Control for AI Agents

This package provides authorization patterns for autonomous AI agent systems
using OpenFGA and Relationship-Based Access Control (ReBAC).
"""

from .auth_service import AgentAuthorizationService
from .gateway import AuthorizationGateway, AuthorizationError
from .scope_inference import ScopeInferenceService
from .caching import CachedAuthorizationService
from .models import AuditEvent, TaskMetadata

__version__ = "0.1.0"
__all__ = [
    "AgentAuthorizationService",
    "CachedAuthorizationService",
    "AuthorizationGateway",
    "AuthorizationError",
    "ScopeInferenceService",
    "AuditEvent",
    "TaskMetadata",
]

