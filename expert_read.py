"""Expert Read — retrieve full instructions for a topic."""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ...db import get_pool

log = structlog.get_logger()


@register_tool
class ExpertReadTool(BaseTool):

    @property
    def name(self) -> str:
        return "expert_read"

    @property
    def description(self) -> str:
        return (
            "Read full expert instructions for a specific topic. "
            "Returns the complete content (procedures, steps, decision trees) "
            "along with any cross-references to related topics. "
            "Call this BEFORE executing any procedure you found in the expert index."
        )

    @property
    def short_description(self) -> str:
        return "Read full expert instructions for a topic"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic name to read (exact match from expert_list or expert_search)",
                },
            },
            "required": ["topic"],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(self, topic: str, **kwargs) -> ToolResult:
        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available")

        slug = self._profile_slug
        if not slug:
            return ToolResult.fail("No profile context — cannot query expert entries")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT topic, category, summary, content, priority, tags, refs
                   FROM expert_entries
                   WHERE profile_slug = $1 AND topic = $2""",
                slug, topic,
            )

        if not row:
            return ToolResult.fail(
                f"No expert entry found for topic '{topic}'. "
                f"Use expert_list or expert_search to find available topics."
            )

        refs = list(row["refs"]) if row["refs"] else []

        return ToolResult.ok({
            "topic": row["topic"],
            "category": row["category"],
            "summary": row["summary"],
            "content": row["content"],
            "priority": row["priority"],
            "tags": list(row["tags"]) if row["tags"] else [],
            "refs": refs,
            "has_refs": len(refs) > 0,
            "hint": (
                "Related topics available: " + ", ".join(refs) + ". "
                "Call expert_read again if you need additional context."
            ) if refs else None,
        })
