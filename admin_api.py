"""
Expert skill — admin API routes for proposals CRUD.

These routes are loaded by the tool-executor when the manifest declares
`admin_api: admin_api.py`. The gatekeeper proxies requests from
/api/expert/{slug}/... to /skill_api/expert/{slug}/... which land here.

Handler signature: async handler(pool, body=None, **regex_groups)
Returns: dict (JSON response). Use __status key for non-200 status codes.
"""

import json
import structlog

log = structlog.get_logger()


async def list_proposals(pool, body=None, slug=None, **kw):
    """List pending expert proposals for a profile."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, action, topic, category, summary, content,
                      priority, tags, refs, rationale, existing_content,
                      status, conversation_id, created_at, resolved_at
               FROM expert_proposals
               WHERE profile_slug = $1 AND status = 'pending'
               ORDER BY created_at DESC""",
            slug,
        )
    return {
        "proposals": [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "topic": r["topic"],
                "category": r["category"],
                "summary": r["summary"],
                "content": r["content"],
                "priority": r["priority"],
                "tags": list(r["tags"]) if r["tags"] else [],
                "refs": list(r["refs"]) if r["refs"] else [],
                "rationale": r["rationale"],
                "existing_content": r["existing_content"],
                "conversation_id": r["conversation_id"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None,
            }
            for r in rows
        ]
    }


async def count_proposals(pool, body=None, slug=None, **kw):
    """Get count of pending proposals (for badge display)."""
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM expert_proposals WHERE profile_slug = $1 AND status = 'pending'",
            slug,
        )
    return {"count": count or 0}


async def approve_proposal(pool, body=None, slug=None, proposal_id=None, **kw):
    """Approve a proposal — creates or updates the actual expert entry."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT action, topic, category, summary, content,
                      priority, tags, refs
               FROM expert_proposals
               WHERE id = $1::uuid AND profile_slug = $2 AND status = 'pending'""",
            proposal_id, slug,
        )
        if not row:
            return {"__status": 404, "detail": "Proposal not found or already resolved"}

        # Upsert the expert entry (works for both create and update)
        await conn.execute(
            """INSERT INTO expert_entries
               (profile_slug, topic, category, summary, content, priority, tags, refs)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (profile_slug, topic) DO UPDATE SET
                   category = EXCLUDED.category,
                   summary = EXCLUDED.summary,
                   content = EXCLUDED.content,
                   priority = EXCLUDED.priority,
                   tags = EXCLUDED.tags,
                   refs = EXCLUDED.refs,
                   updated_at = now()""",
            slug, row["topic"], row["category"],
            row["summary"], row["content"], row["priority"],
            row["tags"] or [], row["refs"] or [],
        )

        # Mark proposal as approved
        await conn.execute(
            """UPDATE expert_proposals SET status = 'approved', resolved_at = now()
               WHERE id = $1::uuid""",
            proposal_id,
        )

    return {"approved": True, "topic": row["topic"], "action": row["action"]}


async def reject_proposal(pool, body=None, slug=None, proposal_id=None, **kw):
    """Reject a proposal."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            """UPDATE expert_proposals SET status = 'rejected', resolved_at = now()
               WHERE id = $1::uuid AND profile_slug = $2 AND status = 'pending'""",
            proposal_id, slug,
        )
    if "UPDATE 0" in result:
        return {"__status": 404, "detail": "Proposal not found or already resolved"}
    return {"rejected": True}


# Route table — loaded by tool-executor's _load_skill_api()
# Pattern format: regex matched against the remainder path after /skill_api/{skill_name}/
# Named groups become kwargs to the handler.
routes = [
    ("GET",  r"/(?P<slug>[\w-]+)/proposals$",                                list_proposals),
    ("GET",  r"/(?P<slug>[\w-]+)/proposals/count$",                          count_proposals),
    ("POST", r"/(?P<slug>[\w-]+)/proposals/(?P<proposal_id>[\w-]+)/approve$", approve_proposal),
    ("POST", r"/(?P<slug>[\w-]+)/proposals/(?P<proposal_id>[\w-]+)/reject$",  reject_proposal),
]
