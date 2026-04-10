-- Hedwig v3.0 Multi-tenant schema
-- Run in Supabase SQL Editor after initial schema

-- ---------------------------------------------------------------------------
-- Add user_id to existing tables
-- ---------------------------------------------------------------------------

ALTER TABLE signals ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE feedback ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE evolution_logs ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE criteria_versions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE user_memory ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- Users profile (extends auth.users)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    onboarding_complete BOOLEAN DEFAULT FALSE,
    criteria JSONB DEFAULT '{}'::jsonb,
    settings JSONB DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Subscriptions (Stripe)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'pro', 'team')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    stripe_price_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'past_due', 'incomplete')),
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Usage tracking (for quota enforcement on free tier)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS usage_tracking (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    metric TEXT NOT NULL,  -- 'signals_collected', 'llm_tokens', 'evolution_cycles'
    value INTEGER DEFAULT 0,
    period_start TIMESTAMPTZ DEFAULT NOW(),
    period_end TIMESTAMPTZ,
    UNIQUE(user_id, metric, period_start)
);

-- ---------------------------------------------------------------------------
-- User-scoped source plugin config
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_sources (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    plugin_id TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}'::jsonb,
    reliability_score FLOAT DEFAULT 1.0,
    custom_endpoints JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, plugin_id)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_signals_user ON signals(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_evolution_user ON evolution_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_criteria_user ON criteria_versions(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_user ON user_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_user_metric ON usage_tracking(user_id, metric);
CREATE INDEX IF NOT EXISTS idx_user_sources_user ON user_sources(user_id);

-- ---------------------------------------------------------------------------
-- Row-Level Security policies
-- ---------------------------------------------------------------------------

-- Enable RLS on all user-scoped tables
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE evolution_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE criteria_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sources ENABLE ROW LEVEL SECURITY;

-- Users can only see their own data
CREATE POLICY "Users see own signals" ON signals FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own signals" ON signals FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users update own signals" ON signals FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users see own feedback" ON feedback FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own feedback" ON feedback FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users see own evolution" ON evolution_logs FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own evolution" ON evolution_logs FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users see own criteria" ON criteria_versions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own criteria" ON criteria_versions FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users see own memory" ON user_memory FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own memory" ON user_memory FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users see own profile" ON user_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users update own profile" ON user_profiles FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users see own subscription" ON subscriptions FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users see own usage" ON usage_tracking FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users see own sources" ON user_sources FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users manage own sources" ON user_sources FOR ALL USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Auto-create user_profile on signup (trigger)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_profiles (id, email)
    VALUES (NEW.id, NEW.email);

    INSERT INTO subscriptions (user_id, tier, status)
    VALUES (NEW.id, 'free', 'active');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();
