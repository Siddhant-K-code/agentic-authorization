"""
Caching layer for authorization decisions to improve performance.
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, Any

from .auth_service import AgentAuthorizationService


class CachedAuthorizationService(AgentAuthorizationService):
    """
    Authorization service with caching for improved performance.

    Authorization checks happen on every tool call, so caching can significantly
    improve performance. Cache entries are invalidated when tasks are revoked.
    """

    def __init__(
        self,
        *args,
        cache_ttl_seconds: int = 60,
        **kwargs
    ):
        """
        Initialize the cached authorization service.

        Args:
            *args: Arguments passed to parent AgentAuthorizationService
            cache_ttl_seconds: Time-to-live for cache entries in seconds
            **kwargs: Keyword arguments passed to parent AgentAuthorizationService
        """
        super().__init__(*args, **kwargs)
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = cache_ttl_seconds

    async def check_agent_resource_access(
        self,
        agent_id: str,
        task_id: str,
        resource_id: str,
        access_type: str = "reader"
    ) -> Tuple[bool, str]:
        """
        Check authorization with caching.

        Cache keys are based on agent_id, task_id, resource_id, and access_type.
        Denials are cached for a shorter duration to allow for quick recovery
        from transient issues.
        """
        cache_key = f"{agent_id}:{task_id}:{resource_id}:{access_type}"

        # Check cache
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if datetime.utcnow() < entry["expires_at"]:
                return entry["result"]

        # Cache miss - perform actual check
        result = await super().check_agent_resource_access(
            agent_id, task_id, resource_id, access_type
        )

        # Cache the result (shorter TTL for denials)
        ttl = self.cache_ttl if result[0] else 10
        self.cache[cache_key] = {
            "result": result,
            "expires_at": datetime.utcnow() + timedelta(seconds=ttl)
        }

        return result

    def invalidate_task_cache(self, task_id: str):
        """Invalidate all cache entries for a task."""
        keys_to_delete = [
            k for k in self.cache.keys()
            if task_id in k
        ]
        for key in keys_to_delete:
            del self.cache[key]

    async def revoke_task(self, task_id: str) -> Dict[str, Any]:
        """Revoke task and invalidate related cache entries."""
        # Invalidate cache first
        self.invalidate_task_cache(task_id)

        # Then revoke the task
        return await super().revoke_task(task_id)

