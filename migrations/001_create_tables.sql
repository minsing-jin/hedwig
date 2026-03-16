-- Hedwig Signal Radar - Supabase Schema
-- Run this in Supabase Dashboard > SQL Editor

CREATE TABLE IF NOT EXISTS signals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content TEXT,
    author TEXT,
    platform_score INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    published_at TIMESTAMPTZ,
    relevance_score FLOAT DEFAULT 0,
    urgency TEXT DEFAULT 'skip',
    why_relevant TEXT,
    devils_advocate TEXT,
    opportunity_note TEXT,
    extra JSONB DEFAULT '{}',
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL,
    content TEXT,
    sentiment TEXT,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS briefings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    type TEXT NOT NULL,  -- 'daily' or 'weekly'
    content TEXT NOT NULL,
    signal_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_platform ON signals(platform);
CREATE INDEX IF NOT EXISTS idx_signals_urgency ON signals(urgency);
CREATE INDEX IF NOT EXISTS idx_feedback_signal ON feedback(signal_id);
CREATE INDEX IF NOT EXISTS idx_briefings_type ON briefings(type, created_at DESC);

-- RLS (Row Level Security) - disabled for personal tool
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefings ENABLE ROW LEVEL SECURITY;

-- Allow all operations with service key (personal tool)
CREATE POLICY "Allow all for service key" ON signals FOR ALL USING (true);
CREATE POLICY "Allow all for service key" ON feedback FOR ALL USING (true);
CREATE POLICY "Allow all for service key" ON briefings FOR ALL USING (true);
