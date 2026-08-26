-- Pro subscription migration (run in Supabase SQL Editor)
-- Adds Pro scan tracking + subscriptions table for ₹999/month tier.

-- 1) Extend user_entitlements for Pro scan counters
ALTER TABLE public.user_entitlements
ADD COLUMN IF NOT EXISTS pro_scans_used integer NOT NULL DEFAULT 0 CHECK (pro_scans_used >= 0),
ADD COLUMN IF NOT EXISTS pro_scans_reset_at timestamptz;

-- 2) Subscriptions table (Pro / Enterprise)
CREATE TABLE IF NOT EXISTS public.subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tier text NOT NULL DEFAULT 'pro' CHECK (tier IN ('pro', 'enterprise')),
  razorpay_subscription_id text UNIQUE,
  razorpay_plan_id text,
  status text NOT NULL DEFAULT 'created' CHECK (
    status IN ('created', 'authenticated', 'active', 'paused', 'halted', 'cancelled', 'completed', 'expired')
  ),
  current_start timestamptz,
  current_end timestamptz,
  charge_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, tier)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status
  ON public.subscriptions (user_id, status);

CREATE INDEX IF NOT EXISTS idx_subscriptions_razorpay
  ON public.subscriptions (razorpay_subscription_id);

ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'subscriptions'
      AND policyname = 'Users read own subscriptions'
  ) THEN
    CREATE POLICY "Users read own subscriptions"
      ON public.subscriptions FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
END $$;
