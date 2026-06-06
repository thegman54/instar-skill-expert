CREATE TABLE IF NOT EXISTS expert_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_slug TEXT NOT NULL,
    category TEXT NOT NULL,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    priority TEXT DEFAULT 'normal',
    refs TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(profile_slug, topic)
);

CREATE INDEX IF NOT EXISTS idx_expert_entries_slug ON expert_entries(profile_slug);
CREATE INDEX IF NOT EXISTS idx_expert_entries_category ON expert_entries(profile_slug, category);
CREATE INDEX IF NOT EXISTS idx_expert_entries_tags ON expert_entries USING GIN(tags);
