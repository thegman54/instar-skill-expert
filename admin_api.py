"""
Expert skill — admin API routes for entries CRUD and proposals.

These routes are loaded by the tool-executor when the manifest declares
`admin_api: admin_api.py`. The gatekeeper proxies requests from
/api/expert/{slug}/... to /skill_api/expert/{slug}/... which land here.

Handler signature: async handler(pool, body=None, **regex_groups)
Returns: dict (JSON response). Use __status key for non-200 status codes.
"""

import json
import os
import structlog

log = structlog.get_logger()

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))


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
# EXPERT LEARNING — Analyze conversation transcripts → proposals
# =============================================================================

ENHANCER_SYSTEM_PROMPT = """\
You are an Expert Knowledge Curator. Your job is to analyze conversation transcripts \
and improve a bot's expert knowledge base by proposing precise, actionable entries.

You will receive:
1. The current expert knowledge entries (what the bot already knows)
2. A conversation transcript (what actually happened)

Your task:
- Identify knowledge gaps: where did the bot struggle, give wrong info, or miss context?
- Identify improvements: where could existing entries be clearer, more complete, or better structured?
- Identify new topics: what knowledge would have helped but doesn't exist yet?

For each proposal, output a JSON object in the "proposals" array with these fields:
- "action": "create" (new topic) or "update" (improve existing)
- "topic": short kebab-case identifier (e.g. "api-auth-flow", "error-handling-timeouts")
- "category": logical grouping (e.g. "api", "workflow", "troubleshooting")
- "summary": one-line description of what this entry covers
- "content": the full knowledge entry in markdown — procedures, examples, gotchas
- "priority": "low", "normal", "high", or "critical"
- "tags": array of searchable keywords
- "refs": array of related topic names (cross-references)
- "rationale": why this change improves the bot's capabilities (reference the transcript)

If an entry already exists and just needs refinement, use action "update" and include \
the improved full content (not a diff).

Respond with ONLY a JSON object: {"proposals": [...]}
No commentary, no markdown fences, just the JSON.\
"""


async def learn_from_transcript(pool, body=None, slug=None, credentials=None, **kw):
    """
    Analyze a conversation transcript against current expert knowledge.
    Calls Claude API directly to produce proposals, writes them to expert_proposals.
    """
    if not body:
        return {"__status": 400, "detail": "Request body required"}

    transcript = (body.get("transcript") or "").strip()
    conversation_id = body.get("conversation_id", "")
    if not transcript:
        return {"__status": 400, "detail": "transcript is required"}

    # Fetch API key from credentials (passed by tool-executor)
    api_key = None
    if credentials:
        try:
            creds = await credentials.get_credentials("expert_learn", ["ANTHROPIC_API_KEY"])
            api_key = creds.get("ANTHROPIC_API_KEY")
        except Exception as e:
            log.warning("learn_credential_fetch_failed", error=str(e))

    if not api_key:
        return {"__status": 503, "detail": "ANTHROPIC_API_KEY not available"}

    # Load current expert entries for context
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT topic, category, summary, content, priority, tags, refs
               FROM expert_entries
               WHERE profile_slug = $1
               ORDER BY category, topic""",
            slug,
        )

    entries_context = ""
    if rows:
        entry_lines = []
        for r in rows:
            entry_lines.append(
                f"### {r['topic']} ({r['category']})\n"
                f"**Summary:** {r['summary']}\n"
                f"**Priority:** {r['priority']}\n"
                f"**Tags:** {', '.join(r['tags']) if r['tags'] else 'none'}\n\n"
                f"{r['content']}\n"
            )
        entries_context = "\n---\n".join(entry_lines)
    else:
        entries_context = "(No expert entries exist yet — all proposals will be creates)"

    user_message = (
        f"## Current Expert Knowledge ({len(rows)} entries)\n\n"
        f"{entries_context}\n\n"
        f"---\n\n"
        f"## Conversation Transcript\n\n"
        f"{transcript}"
    )

    # Call Claude API
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 8192,
                    "system": ENHANCER_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_message}],
                },
                timeout=120.0,
            )
    except Exception as e:
        log.error("learn_api_call_failed", error=str(e))
        return {"__status": 502, "detail": f"Claude API call failed: {e}"}

    if resp.status_code != 200:
        log.error("learn_api_error", status=resp.status_code, body=resp.text[:500])
        return {"__status": 502, "detail": f"Claude API returned {resp.status_code}"}

    # Parse response
    result = resp.json()
    text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    try:
        parsed = json.loads(text)
        proposals = parsed.get("proposals", [])
    except json.JSONDecodeError:
        log.error("learn_parse_failed", text=text[:500])
        return {"__status": 502, "detail": "Claude returned invalid JSON"}

    if not proposals:
        return {"proposals_created": 0, "message": "No improvements identified"}

    # Write proposals to DB
    created = 0
    async with pool.acquire() as conn:
        for p in proposals:
            topic = (p.get("topic") or "").strip()
            if not topic:
                continue

            # For updates, capture existing content for side-by-side diff
            existing_content = None
            if p.get("action") == "update":
                row = await conn.fetchrow(
                    "SELECT content FROM expert_entries WHERE profile_slug = $1 AND topic = $2",
                    slug, topic,
                )
                if row:
                    existing_content = row["content"]

            await conn.execute(
                """INSERT INTO expert_proposals
                   (profile_slug, action, topic, category, summary, content,
                    priority, tags, refs, rationale, existing_content,
                    status, conversation_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pending', $12)""",
                slug,
                p.get("action", "create"),
                topic,
                p.get("category", "general"),
                p.get("summary", ""),
                p.get("content", ""),
                p.get("priority", "normal"),
                p.get("tags", []),
                p.get("refs", []),
                p.get("rationale", ""),
                existing_content,
                conversation_id,
            )
            created += 1

    log.info("learn_proposals_created", slug=slug, count=created, conversation_id=conversation_id)
    return {"proposals_created": created}


# =============================================================================
# LEARN INSTRUCTIONS — read/write instructions_learn.md
# =============================================================================

async def get_learn_instructions(pool, body=None, **kw):
    """Read the learn instructions file."""
    path = os.path.join(_SKILL_DIR, 'instructions_learn.md')
    if os.path.isfile(path):
        with open(path, 'r') as f:
            return {"content": f.read()}
    return {"content": ""}


async def save_learn_instructions(pool, body=None, **kw):
    """Write the learn instructions file."""
    if not body or "content" not in body:
        return {"__status": 400, "detail": "content is required"}
    path = os.path.join(_SKILL_DIR, 'instructions_learn.md')
    with open(path, 'w') as f:
        f.write(body["content"])
    log.info("learn_instructions_saved", skill="expert", chars=len(body["content"]))
    return {"saved": True}


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
    # Learning
    ("POST",   r"/(?P<slug>[\w-]+)/learn$",                                    learn_from_transcript),
    # Learn instructions
    ("GET",    r"/learn-instructions$",                                         get_learn_instructions),
    ("PUT",    r"/learn-instructions$",                                         save_learn_instructions),
]
