"""Expert Search — fuzzy match across expert knowledge base."""

import structlog

from ..base import BaseTool, ToolResult
from ..registry import register_tool
from ...db import get_pool

log = structlog.get_logger()


@register_tool
class ExpertSearchTool(BaseTool):

    @property
    def name(self) -> str:
        return "expert_search"

    @property
    def description(self) -> str:
        return (
            "Search expert knowledge by keyword. Matches against topic names, "
            "summaries, tags, and content. Use this when you're not sure which "
            "topic applies to the current situation."
        )

    @property
    def short_description(self) -> str:
        return "Search expert knowledge by keyword"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — matches topic, summary, tags, and content",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 10,
                },
            },
            "required": ["query"],
        }

    def credential_keys(self) -> list[str]:
        return []

    async def execute(self, query: str, limit: int = 10, **kwargs) -> ToolResult:
        pool = get_pool()
        if not pool:
            return ToolResult.fail("Database not available")

        slug = self._profile_slug
        if not slug:
            return ToolResult.fail("No profile context — cannot query expert entries")

        # Search across topic, summary, tags, content with ranking
        # Priority: exact topic match > tag match > summary match > content match
        search_pattern = f"%{query}%"

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT topic, category, summary, priority, tags, refs,
                       CASE
                           WHEN topic ILIKE $2 THEN 4
                           WHEN $3 = ANY(tags) THEN 3
                           WHEN summary ILIKE $2 THEN 2
                           WHEN content ILIKE $2 THEN 1
                           ELSE 0
                       END AS relevance
                   FROM expert_entries
                   WHERE profile_slug = $1
                     AND (
                         topic ILIKE $2
                         OR summary ILIKE $2
                         OR content ILIKE $2
                         OR $3 = ANY(tags)
                     )
                   ORDER BY relevance DESC, priority DESC, topic
                   LIMIT $4""",
                slug, search_pattern, query.lower(), limit,
            )

        results = [
            {
                "topic": r["topic"],
                "category": r["category"],
                "summary": r["summary"],
                "priority": r["priority"],
                "tags": list(r["tags"]) if r["tags"] else [],
                "relevance": r["relevance"],
            }
            for r in rows
        ]

        return ToolResult.ok({
            "query": query,
            "total": len(results),
            "results": results,
            "hint": "Use expert_read(topic) to get full instructions for any result." if results else "No matching topics found.",
        })
