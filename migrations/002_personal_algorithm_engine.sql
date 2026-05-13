-- Personal Algorithm Engine additive schema.
-- Raw events stay in behavior_events; derived rewards are separate.

ALTER TABLE behavior_events
    ADD COLUMN IF NOT EXISTS feed_mode TEXT DEFAULT 'grid';

ALTER TABLE behavior_events
    DROP CONSTRAINT IF EXISTS behavior_events_event_type_check;

ALTER TABLE behavior_events
    ADD CONSTRAINT behavior_events_event_type_check CHECK (event_type IN (
        'view_start','view_end','dwell','skip','share','save',
        'expand_source','click_link','open_qa','card_impression',
        'viewed_card','open','swipe_left','swipe_right','swipe_next',
        'not_interested'
    ));

CREATE TABLE IF NOT EXISTS behavior_rewards (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id TEXT NOT NULL,
    raw_event_id TEXT,
    event_type TEXT NOT NULL,
    reward_value FLOAT NOT NULL,
    signal_strength TEXT NOT NULL,
    policy_version INTEGER DEFAULT 1,
    feed_mode TEXT DEFAULT 'grid',
    source TEXT DEFAULT 'personal_algorithm',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_behavior_mode ON behavior_events(feed_mode, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_reward_signal ON behavior_rewards(signal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reward_strength ON behavior_rewards(signal_strength, created_at DESC);
