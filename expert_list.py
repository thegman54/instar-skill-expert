"""Expert List — browse available expert topics."""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ...db import get_pool

log = structlog.get_logger()


@register_tool
class ExpertListTool(BaseTool):

    @property
    def name(self) -> str:
        return "expert_list"

    @property
    def description(self) -> str:
        return (
            "List available expert knowledge topics. "
            "Optionally filter by category. Returns topic names, summaries, "
            "priorities, and categories — use this to find what's available "
            "before calling expert_read for full instructions."
        )

    @property
    def short_description(self) -> str:
        return "Browse expert knowledge topics"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category (optional). Omit to list all.",
                },
            },
            "required": [],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(self, category: str = None, **kwargs) -> ToolResult:
        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available")

        slug = self._profile_slug
        if not slug:
            return ToolResult.fail("No profile context — cannot query expert entries")

        async with pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    """SELECT topic, category, summary, priority, tags, refs
                       FROM expert_entries
                       WHERE profile_slug = $1 AND category = $2
                       ORDER BY priority DESC, topic""",
                    slug, category,
                )
            else:
                rows = await conn.fetch(
                    """SELECT topic, category, summary, priority, tags, refs
                       FROM expert_entries
                       WHERE profile_slug = $1
                       ORDER BY category, priority DESC, topic""",
                    slug,
                )

        entries = [
            {
                "topic": r["topic"],
                "category": r["category"],
                "summary": r["summary"],
                "priority": r["priority"],
                "tags": list(r["tags"]) if r["tags"] else [],
                "refs": list(r["refs"]) if r["refs"] else [],
            }
            for r in rows
        ]

        # Group by category for readability
        categories = {}
        for e in entries:
            cat = e["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(e)

        return ToolResult.ok({
            "profile_slug": slug,
            "total": len(entries),
            "categories": categories,
        })
