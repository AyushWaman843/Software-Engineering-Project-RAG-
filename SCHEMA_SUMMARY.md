# Database Schema for Pro Subscription

## What's New (Changes from Original)

### 1. `user_entitlements` table - UPDATED
**Added columns for Pro subscription tracking**:

```sql
-- ADDED:
pro_scans_used integer NOT NULL DEFAULT 0 CHECK (pro_scans_used >= 0)
pro_scans_reset_at timestamptz
```

**Purpose**:
- `pro_scans_used`: Tracks how many Pro scans used this billing period (0-5)
- `pro_scans_reset_at`: When scans reset (subscription anniversary date, not 1st of month)

### 2. `subscriptions` table - NEW TABLE
**Entirely new table for managing Pro/Enterprise subscriptions**:

```sql
CREATE TABLE IF NOT EXISTS public.subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tier text NOT NULL DEFAULT 'pro' CHECK (tier IN ('pro', 'enterprise')),
  razorpay_subscription_id text UNIQUE,
  razorpay_plan_id text,
  status text NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'authenticated', 'active', 'paused', 'halted', 'cancelled', 'completed', 'expired')),
  current_start timestamptz,
  current_end timestamptz,
  charge_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, tier)
);

CREATE INDEX idx_subscriptions_user_status ON public.subscriptions (user_id, status);
CREATE INDEX idx_subscriptions_razorpay ON public.subscriptions (razorpay_subscription_id);

ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own subscriptions"
  ON public.subscriptions FOR SELECT
  USING (auth.uid() = user_id);
```

**Purpose**:
- Tracks Pro subscriptions (status, billing dates, Razorpay IDs)
- Supports future Enterprise tier
- One active subscription per user per tier

## Complete Schema (Full File)

See `supabase/schema.sql` - no changes needed if you already ran it.

## Migration Guide (If Not Applied Yet)

### Run in Supabase SQL Editor:

```sql
-- 1. Update user_entitlements (if table already exists)
ALTER TABLE public.user_entitlements 
ADD COLUMN IF NOT EXISTS pro_scans_used integer NOT NULL DEFAULT 0 CHECK (pro_scans_used >= 0),
ADD COLUMN IF NOT EXISTS pro_scans_reset_at timestamptz;

-- 2. Create subscriptions table (copy from schema.sql lines 104-130)
-- Run the full CREATE TABLE statement for subscriptions
```

### Or Fresh Setup:
```sql
-- Run entire supabase/schema.sql file (includes all tables)
```

## Data Flow

### New User Subscribes to Pro:
1. User clicks "Subscribe to Pro" → `POST /api/subscription/pro/create`
2. Backend creates Razorpay subscription
3. User pays via Razorpay hosted checkout
4. Razorpay sends `subscription.activated` webhook
5. Backend:
   - Inserts row in `subscriptions` (status='active')
   - Sets `pro_scans_used=0` in `user_entitlements`
   - Sets `pro_scans_reset_at` = now + 1 month

### User Runs a Scan:
1. Backend checks: Pro subscription active? → Yes
2. Backend checks: `pro_scans_used < 5`? → Yes
3. Consume Pro scan:
   - Increment `pro_scans_used`
   - Grant full report access automatically
4. User scans with Pro (no ₹299 payment needed)

### Monthly Reset (Automatic):
1. User runs scan after `pro_scans_reset_at` date
2. Backend sees reset date passed
3. Backend calls `reset_pro_scan_counter()`:
   - Sets `pro_scans_used = 0`
   - Sets `pro_scans_reset_at` = now + 1 month
4. User has 5 fresh scans

### Subscription Renewal (Razorpay Automatic):
1. Razorpay charges user on anniversary date
2. Razorpay sends `subscription.charged` webhook
3. Backend updates `subscriptions` table dates
4. Scans continue resetting monthly

## Key Differences from Original Design

| Aspect | Original Plan | Final Implementation |
|--------|--------------|---------------------|
| Reset timing | 1st of every month | Subscription anniversary (prevents gaming) |
| Plan storage | Create plan each time | Store in env, reuse (production-ready) |
| Checkout flow | Alert placeholder | Real Razorpay subscription checkout |
| Price display | Small ribbon text | Prominent strikethrough + SAVE badge |

## Summary

**Existing tables**: 5 (unchanged)
**New tables**: 1 (`subscriptions`)
**Updated tables**: 1 (`user_entitlements` + 2 columns)

**Total tables**: 7
