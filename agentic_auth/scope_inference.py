"""
Scope inference service for determining required resource access from natural language.
"""

import json
import re
from typing import Dict, List, Any, Optional

from anthropic import Anthropic


class ScopeInferenceService:
    """
    Infer required resource scopes from natural language task descriptions.

    This service uses an LLM to analyze user requests and determine the minimal
    set of resources and permissions needed to complete the task.
    """

    SCOPE_INFERENCE_PROMPT = """Analyze the user's request and determine the minimal required resource access.

User request: {request}

Available resource types:
- email: Gmail messages (scopes: read, send, delete)
- calendar: Google Calendar (scopes: read, write)
- documents: Google Docs (scopes: read, write)
- slack: Slack channels (scopes: read, write)
- linear: Linear issues (scopes: read, write)

Output a JSON object with:
{{
  "resources": [
    {{
      "type": "resource_type",
      "id": "specific_id or pattern",
      "access": "read or write",
      "constraints": {{
        "time_range": "if applicable",
        "filters": ["any filters"]
      }}
    }}
  ],
  "reasoning": "brief explanation of why these resources are needed"
}}

Be minimal: only include resources strictly necessary for the task.
Prefer read access over write access unless modification is explicitly requested."""

    def __init__(self, anthropic_client: Anthropic, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize the scope inference service.

        Args:
            anthropic_client: Configured Anthropic client
            model: Model to use for inference (default: claude-sonnet-4-20250514)
        """
        self.client = anthropic_client
        self.model = model

    async def infer_scopes(
        self,
        user_request: str,
        available_resources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Infer minimal required scopes from a natural language request.

        Args:
            user_request: Natural language description of what the user wants
            available_resources: List of resources the user has access to
                Each resource should have: {"type": str, "id": str, ...}

        Returns:
            Dictionary with inferred resources and reasoning:
            {
                "resources": [...],
                "reasoning": str,
                "original_request": str
            }
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": self.SCOPE_INFERENCE_PROMPT.format(
                    request=user_request
                )
            }]
        )

        # Parse the response
        scope_text = response.content[0].text

        # Extract JSON from response
        start = scope_text.find('{')
        end = scope_text.rfind('}') + 1

        if start == -1 or end == 0:
            # Fallback: return empty resources if JSON parsing fails
            return {
                "resources": [],
                "reasoning": "Failed to parse LLM response",
                "original_request": user_request
            }

        try:
            scope_data = json.loads(scope_text[start:end])
        except json.JSONDecodeError:
            return {
                "resources": [],
                "reasoning": "Invalid JSON in LLM response",
                "original_request": user_request
            }

        # Validate against available resources
        validated_resources = []
        for resource in scope_data.get("resources", []):
            if self._resource_available(resource, available_resources):
                validated_resources.append(resource)

        return {
            "resources": validated_resources,
            "reasoning": scope_data.get("reasoning", ""),
            "original_request": user_request
        }

    def _resource_available(
        self,
        requested: Dict[str, Any],
        available: List[Dict[str, Any]]
    ) -> bool:
        """Check if a requested resource is in the available set."""
        for avail in available:
            if (avail.get("type") == requested.get("type") and
                self._id_matches(requested.get("id", ""), avail.get("id", ""))):
                return True
        return False

    def _id_matches(self, requested_id: str, available_id: str) -> bool:
        """Check if a requested resource ID matches an available one."""
        if requested_id == available_id:
            return True
        if "*" in available_id:
            pattern = available_id.replace("*", ".*")
            return bool(re.match(pattern, requested_id))
        return False

