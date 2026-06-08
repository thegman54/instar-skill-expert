"""Expert Propose — stage expert entry changes for owner review."""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ...db import get_pool

log = structlog.get_logger()


@register_tool
class ExpertProposeTool(BaseTool):

    @property
    def name(self) -> str:
        return "expert_propose"

    @property
    def description(self) -> str:
        return (
            "Propose a new or updated expert entry for owner review. "
            "Use this after analyzing a conversation to suggest knowledge improvements. "
            "Proposals are staged for approval — they do NOT take effect immediately. "
            "For updates, the current content is automatically captured for comparison."
        )

    @property
    def short_description(self) -> str:
        return "Propose expert entry changes for owner approval"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update"],
                    "description": "Whether to create a new entry or update an existing one",
                },
                "topic": {
                    "type": "string",
                    "description": "The topic name (must match existing topic for updates)",
                },
                "category": {
                    "type": "string",
                    "description": "Category for the entry (e.g., 'api_endpoints', 'troubleshooting')",
                },
                "summary": {
                    "type": "string",
                    "description": "One-line summary of the entry",
                },
                "content": {
                    "type": "string",
                    "description": "Full content — procedures, steps, decision trees, etc.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                    "description": "Priority level (default: normal)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for searchability",
                },
                "refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cross-references to related topics",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this change would improve expert knowledge — what gap or issue it addresses",
                },
            },
            "required": ["action", "topic", "content", "rationale"],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(
        self,
        action: str,
        topic: str,
        content: str,
        rationale: str,
        category: str = None,
        summary: str = None,
        priority: str = "normal",
        tags: list = None,
        refs: list = None,
        **kwargs,
    ) -> ToolResult:
        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available")

        slug = self._profile_slug
        if not slug:
            return ToolResult.fail("No profile context — cannot propose expert changes")

        if action not in ("create", "update"):
            return ToolResult.fail("action must be 'create' or 'update'")

        existing_content = None

        async with pool.acquire() as conn:
            # For updates, fetch current entry to store existing content
            if action == "update":
                row = await conn.fetchrow(
                    """SELECT content, category, summary FROM expert_entries
                       WHERE profile_slug = $1 AND topic = $2""",
                    slug, topic,
                )
                if not row:
                    return ToolResult.fail(
                        f"Cannot update — no existing entry for topic '{topic}'. "
                        f"Use action='create' for new entries."
                    )
                existing_content = row["content"]
                # Default category/summary from existing entry if not provided
                if not category:
                    category = row["category"]
                if not summary:
                    summary = row["summary"]

            # Get conversation_id from context if available
            conversation_id = kwargs.get("_conversation_id", "")

            await conn.execute(
                """INSERT INTO expert_proposals
                   (profile_slug, action, topic, category, summary, content,
                    priority, tags, refs, rationale, existing_content, conversation_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                slug, action, topic, category or "uncategorized", summary or "",
                content, priority, tags or [], refs or [], rationale,
                existing_content, conversation_id,
            )

        action_label = "New entry" if action == "create" else "Update to existing entry"
        return ToolResult.ok({
            "status": "staged",
            "action": action,
            "topic": topic,
            "message": f"{action_label} for '{topic}' has been staged for owner review. "
                       f"It will appear in the expert admin panel under Suggestions.",
        })
