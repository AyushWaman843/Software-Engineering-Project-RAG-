# Pro Subscription Tier - Implementation Guide

## Overview

The Pro subscription tier has been successfully added to the DPDP Scanner app:

- **Price**: ₹999/month (recurring)
- **Display**: ₹1,175 with "15% off" badge
- **Benefits**: 5 full-report scans per month
- **Reset**: Scans reset on the 1st of each month
- **Payment**: Razorpay Subscriptions

## What Was Implemented

### 1. Database Schema (`supabase/schema.sql`)

Added new tables and columns:

- **`subscriptions` table**: Tracks Pro/Enterprise subscriptions
  - Fields: `razorpay_subscription_id`, `status`, `current_start`, `current_end`, etc.
  
- **`user_entitlements` table** (updated):
  - Added `pro_scans_used` (tracks scans consumed this month)
  - Added `pro_scans_reset_at` (next reset date, 1st of next month)

**Migration needed**: Run the updated `schema.sql` in Supabase SQL Editor.

### 2. Backend Changes

#### New Files:
- **`razorpay_subscriptions.py`**: Razorpay subscription creation/management
- **`supabase_subscriptions.py`**: Pro subscription database operations

#### Updated Files:
- **`config.py`**: Added Pro subscription config vars
- **`.env`**: Added `PRO_SUBSCRIPTION_ENABLED`, `PRO_PRICE_PAISE`, etc.
- **`razorpay_webhooks.py`**: Handles `subscription.*` webhook events
- **`supabase_entitlements.py`**: Updated `consume_user_scan()` to prioritize Pro scans
- **`scan_quota.py`**: Updated `quota_snapshot()` to include Pro info
- **`user_reconcile.py`**: Pro users get auto-access to their own reports
- **`entitlements.py`**: Pro scans auto-unlock full reports
- **`app.py`**: Added 3 new API endpoints:
  - `POST /api/subscription/pro/create` - Create Pro subscription
  - `GET /api/subscription/status` - Get subscription status
  - `POST /api/subscription/cancel` - Cancel subscription
- **`requirements.txt`**: Added `python-dateutil>=2.8.0`

#### Scan Priority Order:
1. **Pro scans** (if active Pro subscription)
2. **Free scans** (1 lifetime)
3. **Prepaid scans** (pay-before-scan ₹299)

### 3. Frontend Changes

#### Updated Components:
- **`TierComparisonModal.tsx`**: Added Pro tier card with 15% off badge
- **`ScanQuotaBanner.tsx`**: Shows Pro scan count ("Pro: 3 of 5 scans remaining")
- **`types.ts`**: Added `pro_scans_remaining` and `has_pro` to `QuotaInfo`

#### UI Features:
- Pro tier displayed between Free and One-Time Report
- Green ribbon with "₹1,175 (strikethrough) 15% off"
- Pro subscription button (placeholder - needs Razorpay flow implementation)
- Shows remaining Pro scans in quota banner

## Setup Instructions

### 1. Database Migration

Run in Supabase SQL Editor:

```sql
-- Add pro_scans_used and pro_scans_reset_at to user_entitlements
ALTER TABLE public.user_entitlements 
ADD COLUMN IF NOT EXISTS pro_scans_used integer NOT NULL DEFAULT 0 CHECK (pro_scans_used >= 0),
ADD COLUMN IF NOT EXISTS pro_scans_reset_at timestamptz;

-- Create subscriptions table (see schema.sql for full definition)
-- Copy the subscriptions table DDL from supabase/schema.sql
```

### 2. Environment Variables

Update `.env`:

```bash
PRO_SUBSCRIPTION_ENABLED=1
PRO_PRICE_PAISE=99900        # ₹999.00
PRO_ORIGINAL_PRICE_PAISE=117500  # ₹1,175 (for 15% off display)
PRO_SCANS_PER_MONTH=5
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Razorpay Configuration

#### Create a Pro Plan (one-time):

```python
from razorpay_subscriptions import create_pro_subscription_plan

# Run once to create the plan
plan = create_pro_subscription_plan()
print(f"Plan ID: {plan['id']}")
# Store plan_id in env or DB for reuse
```

#### Configure Webhook Events:

In Razorpay Dashboard → Webhooks, enable these events:
- `subscription.activated`
- `subscription.charged`
- `subscription.cancelled`
- `subscription.completed`
- `subscription.halted`
- `subscription.paused`

## How It Works

### Pro Subscription Flow:

1. **User subscribes**:
   - Clicks "Subscribe to Pro" in pricing modal
   - Frontend calls `POST /api/subscription/pro/create`
   - Backend creates Razorpay subscription
   - User completes payment via Razorpay checkout

2. **Subscription activated**:
   - Razorpay sends `subscription.activated` webhook
   - Backend saves subscription to `subscriptions` table
   - Initializes `pro_scans_used=0` and sets `pro_scans_reset_at` to 1st of next month

3. **User runs a scan**:
   - Backend checks Pro subscription first in `consume_user_scan()`
   - If active Pro + scans remaining → consumes Pro scan
   - Pro scan increments `pro_scans_used`
   - Report automatically gets full access (no ₹299 payment needed)

4. **Monthly reset**:
   - When user scans after `pro_scans_reset_at` date
   - Backend auto-resets `pro_scans_used=0`
   - Sets next reset to 1st of next month

5. **Subscription renewal**:
   - Razorpay handles recurring billing
   - Sends `subscription.charged` webhook
   - Backend updates subscription dates

### Free Scans with Pro:

- **Pro scans DON'T consume free scans**
- Pro users can still use their 1 free scan as a preview
- Scan priority: Pro → Free → Prepaid

## Testing

### Manual Test Flow:

1. **Database setup**:
   ```bash
   # Run schema migrations in Supabase
   ```

2. **Create test subscription**:
   ```bash
   curl -X POST http://localhost:5000/api/subscription/pro/create \
     -H "X-User-Id: test-user-123" \
     -H "X-API-Key: your-api-key"
   ```

3. **Simulate webhook** (testing without payment):
   ```python
   # Manually insert subscription in DB
   from supabase_subscriptions import upsert_subscription, initialize_pro_subscription_scans
   from datetime import datetime, timezone
   
   upsert_subscription(
       user_id="test-user-123",
       razorpay_subscription_id="sub_test123",
       razorpay_plan_id="plan_test123",
       status="active",
       current_start=datetime.now(timezone.utc),
   )
   initialize_pro_subscription_scans("test-user-123")
   ```

4. **Test scan consumption**:
   - Run 5 scans with the test user
   - Verify all get full reports automatically
   - Check quota shows "Pro: X of 5 scans remaining"

5. **Test monthly reset**:
   ```python
   # Set reset date to past, then trigger scan
   # Verify counter resets to 0
   ```

## Known Limitations / TODOs

1. **Frontend checkout flow**: 
   - Pro subscribe button shows alert (placeholder)
   - Need to implement Razorpay subscription checkout UI
   - Razorpay provides `short_url` for hosted checkout page

2. **Plan management**:
   - Currently creates new plan on each call
   - Should store plan_id and reuse it

3. **Cancellation UX**:
   - API endpoint exists but no UI yet
   - Add "Manage Subscription" button for Pro users

4. **Email notifications**:
   - No email sent on subscription start/renewal/cancel
   - Consider adding email via Razorpay webhooks

5. **Enterprise tier**:
   - Schema supports it (`tier='enterprise'`)
   - Not implemented yet

## Deployment Checklist

- [ ] Run database migrations in Supabase
- [ ] Update `.env` with Pro pricing config
- [ ] Install `python-dateutil` dependency
- [ ] Create Razorpay Pro plan (store plan_id)
- [ ] Configure Razorpay webhook events
- [ ] Test subscription creation end-to-end
- [ ] Test webhook delivery
- [ ] Test monthly reset logic
- [ ] Implement frontend checkout flow
- [ ] Add cancellation UI
- [ ] Update documentation

## Support & Troubleshooting

### Common Issues:

**"Subscriptions are not available"**
- Check `PRO_SUBSCRIPTION_ENABLED=1` in `.env`
- Verify Razorpay keys are set

**Pro scans not working**
- Check subscription status: `GET /api/subscription/status`
- Verify `subscriptions` table has `status='active'`
- Check `pro_scans_used` < 5

**Scans not resetting**
- Verify `pro_scans_reset_at` is set
- Check system clock / timezone
- Look for errors in `reset_pro_scan_counter()`

### Debug Commands:

```python
# Check user's Pro subscription
from supabase_subscriptions import get_active_subscription, get_pro_scans_remaining

sub = get_active_subscription("user-id")
print(sub)

remaining = get_pro_scans_remaining("user-id")
print(f"Remaining: {remaining}")
```

## Future Enhancements

- **Team/Enterprise plans**: Multi-user Pro subscriptions
- **Annual pricing**: Offer yearly discount (e.g., ₹9,999/year)
- **Usage analytics**: Dashboard for Pro users
- **White-label PDFs**: Custom branding for Enterprise
- **API access**: Pro users get API keys for automation
- **Priority support**: Dedicated support channel
- **Rollover scans**: Allow unused scans to carry over (optional)

---

**Version**: 1.0  
**Last Updated**: 2026-07-02  
**Author**: Cursor AI Agent
