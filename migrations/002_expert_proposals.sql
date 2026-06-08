-- Expert proposals — staged suggestions from bot self-analysis.
-- Same propose → approve pattern as bot_memory.staging.
-- Bot calls expert_propose tool → row lands here as pending.
-- Owner reviews in expert admin UI → approves or rejects.

CREATE TABLE IF NOT EXISTS expert_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_slug TEXT NOT NULL,
    action TEXT NOT NULL,              -- 'create' or 'update'
    topic TEXT NOT NULL,
    category TEXT,
    summary TEXT,
    content TEXT,
    priority TEXT DEFAULT 'normal',
    tags TEXT[] DEFAULT '{}',
    refs TEXT[] DEFAULT '{}',
    rationale TEXT,                     -- why this change helps
    existing_content TEXT,             -- current content if action=update
    status TEXT DEFAULT 'pending',     -- pending, approved, rejected
    conversation_id TEXT,              -- which conversation triggered this
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_expert_proposals_pending
    ON expert_proposals(profile_slug, status);

CREATE INDEX IF NOT EXISTS idx_expert_proposals_topic
    ON expert_proposals(profile_slug, topic);
