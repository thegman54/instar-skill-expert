"""
Expert skill — admin API routes for entries CRUD and proposals.

These routes are loaded by the tool-executor when the manifest declares
`admin_api: admin_api.py`. The gatekeeper proxies requests from
/api/expert/{slug}/... to /skill_api/expert/{slug}/... which land here.

Handler signature: async handler(pool, body=None, **regex_groups)
Returns: dict (JSON response). Use __status key for non-200 status codes.
"""

import structlog

log = structlog.get_logger()


# =============================================================================
# ENTRIES CRUD
# =============================================================================

async def list_entries(pool, body=None, slug=None, **kw):
    """List all expert entries for a profile."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, topic, category, summary, content, priority, tags, refs,
                      created_at, updated_at
               FROM expert_entries
               WHERE profile_slug = $1
               ORDER BY category, priority DESC, topic""",
            slug,
        )
    return {
        "entries": [
            {
                "id": str(r["id"]),
                "topic": r["topic"],
                "category": r["category"],
                "summary": r["summary"],
                "content": r["content"],
                "priority": r["priority"],
                "tags": list(r["tags"]) if r["tags"] else [],
                "refs": list(r["refs"]) if r["refs"] else [],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]
    }


async def create_entry(pool, body=None, slug=None, **kw):
    """Create a new expert entry."""
    if not body:
        return {"__status": 400, "detail": "Request body required"}

    topic = (body.get("topic") or "").strip()
    category = (body.get("category") or "").strip()
    summary = (body.get("summary") or "").strip()
    content = (body.get("content") or "").strip()
    priority = body.get("priority", "normal")
    tags = body.get("tags", [])
    refs = body.get("refs", [])

    if not topic or not category or not summary or not content:
        return {"__status": 400, "detail": "topic, category, summary, and content are required"}

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO expert_entries
                   (profile_slug, topic, category, summary, content, priority, tags, refs)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   RETURNING id""",
                slug, topic, category, summary, content, priority, tags, refs,
            )
        except Exception as e:
            if "unique" in str(e).lower():
                return {"__status": 409, "detail": f"Topic '{topic}' already exists for this profile"}
            raise

    return {"id": str(row["id"]), "topic": topic}


async def update_entry(pool, body=None, slug=None, entry_id=None, **kw):
    """Update an existing expert entry."""
    if not body:
        return {"__status": 400, "detail": "Request body required"}

    updates = []
    params = []
    idx = 3  # $1 = entry_id, $2 = profile_slug
    for field in ["category", "summary", "content", "priority"]:
        if field in body:
            updates.append(f"{field} = ${idx}")
            params.append(body[field])
            idx += 1
    if "tags" in body:
        updates.append(f"tags = ${idx}")
        params.append(body["tags"])
        idx += 1
    if "refs" in body:
        updates.append(f"refs = ${idx}")
        params.append(body["refs"])
        idx += 1
    if not updates:
        return {"__status": 400, "detail": "No fields to update"}

    updates.append("updated_at = now()")
    sql = f"UPDATE expert_entries SET {', '.join(updates)} WHERE id = $1::uuid AND profile_slug = $2"
    async with pool.acquire() as conn:
        await conn.execute(sql, entry_id, slug, *params)
    return {"id": entry_id, "updated": True}


async def delete_entry(pool, body=None, slug=None, entry_id=None, **kw):
    """Delete an expert entry."""
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM expert_entries WHERE id = $1::uuid AND profile_slug = $2",
            entry_id, slug,
        )
    return {"deleted": True}


# =============================================================================
# PROPOSALS
# =============================================================================

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


# =============================================================================
# ROUTE TABLE
# =============================================================================

routes = [
    # Entries CRUD
    ("GET",    r"/(?P<slug>[\w-]+)/entries$",                                   list_entries),
    ("POST",   r"/(?P<slug>[\w-]+)/entries$",                                   create_entry),
    ("PUT",    r"/(?P<slug>[\w-]+)/entries/(?P<entry_id>[\w-]+)$",              update_entry),
    ("DELETE", r"/(?P<slug>[\w-]+)/entries/(?P<entry_id>[\w-]+)$",              delete_entry),
    # Proposals
    ("GET",    r"/(?P<slug>[\w-]+)/proposals$",                                 list_proposals),
    ("GET",    r"/(?P<slug>[\w-]+)/proposals/count$",                           count_proposals),
    ("POST",   r"/(?P<slug>[\w-]+)/proposals/(?P<proposal_id>[\w-]+)/approve$", approve_proposal),
    ("POST",   r"/(?P<slug>[\w-]+)/proposals/(?P<proposal_id>[\w-]+)/reject$",  reject_proposal),
]
