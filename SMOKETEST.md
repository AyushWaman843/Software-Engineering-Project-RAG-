# Pre-launch smoke test checklist

Run this manually before marking the DPDP scanner **live**.  
Adjust scan-count steps if your `FREE_SCANS_PER_USER` differs from the default (see step 3).

**Default:** `FREE_SCANS_PER_USER=1` (one free preview scan per account).  
**Demo with 3 scans:** set `FREE_SCANS_PER_USER=3` in `.env`, restart the API, and follow the “3 scans” variant in steps 3 and 7.

---

## 0. Environment

- [ ] `RAZORPAY_WEBHOOK_SECRET` set in `.env` (from Razorpay Dashboard → Webhooks)
- [ ] Webhook URL configured in Razorpay: `https://<your-domain>/api/webhooks/razorpay` (events: **payment.captured**)
- [ ] `FLASK_SECRET_KEY` set for production
- [ ] `INTERNAL_API_KEY` in `web/.env.local` matches root `API_KEY`
- [ ] Supabase schema migrated (`supabase/schema.sql` or `migrate_missing_tables.sql`)

---

## 1. Clean slate (auth reset)

**Option A — script (preferred):**

```powershell
cd dpdp_comp
.\venv\Scripts\activate
python scripts/reset_all_data.py
```

**Option B — Supabase SQL Editor:** run `supabase/reset_all_data.sql`.

Also clear local webhook ledger if present: delete `processed_webhook_payments.json` under `DATA_DIR` (the reset script does this automatically).

- [ ] Public tables empty (`user_scans`, `report_unlocks`, `user_entitlements`)
- [ ] No auth users remain (or only test accounts you intend to keep)
- [ ] Local report JSON files no longer have `premium_unlocked` flags

---

## 2. Sign up

- [ ] Open the app, create a new account (email + password)
- [ ] Confirm email if Supabase requires verification
- [ ] Sign in successfully

---

## 3. Free scan quota

**If `FREE_SCANS_PER_USER=1` (default):**

- [ ] Quota banner shows **1 free preview scan** remaining
- [ ] Run one scan → preview report loads

**If `FREE_SCANS_PER_USER=3`:**

- [ ] Quota banner shows **3 free preview scans**
- [ ] Run first scan → preview report loads

---

## 4. Preview report

- [ ] Score and verdict visible
- [ ] Only top missing indicators shown (preview gate)
- [ ] Full indicator list / AI detail / remediation blocked behind paywall

---

## 5. PDF blocked on preview

- [ ] PDF download blocked or prompts unlock on preview report

---

## 6. One-Time Report unlock (₹299)

- [ ] Click **Unlock Full Report — ₹299**
- [ ] Pay with Razorpay **test card** (or live card in production)
- [ ] UI shows **Verifying payment…** then full report
- [ ] All indicators, AI analysis, remediation visible
- [ ] PDF downloads successfully
- [ ] Free scan quota **unchanged** (unlock does not grant extra free scans)

---

## 7. Exhaust free quota

**`FREE_SCANS_PER_USER=1`:** after step 4, quota should already be exhausted — skip extra scans.

**`FREE_SCANS_PER_USER=3`:** run 2 more free scans, then attempt a 4th:

- [ ] Quota exhausted banner appears
- [ ] New scan blocked until payment or unlock from history

---

## 8. Paid new scan (₹299)

- [ ] Click **Scan new site — ₹299** (or equivalent CTA when quota exhausted)
- [ ] Complete Razorpay payment
- [ ] **Verifying payment…** then scan starts
- [ ] New report **auto-unlocks** (full tier) on completion

---

## 9. Session persistence

- [ ] Sign out, sign back in
- [ ] Previously unlocked reports still show **full** tier
- [ ] Scan history lists past assessments

---

## 10. Forgot password

- [ ] Sign out
- [ ] Sign-in modal → **Forgot password?**
- [ ] Enter email → success message shown
- [ ] Open reset link from email
- [ ] Set new password on `/auth/reset-password`
- [ ] Sign in with new password

---

## 11. Webhook-only unlock (optional)

Simulate a captured payment without relying on the browser unlock call:

1. Create checkout for a preview report (note `order_id` in Razorpay Dashboard or server logs).
2. Complete payment in Razorpay test mode **or** send a test webhook from Razorpay Dashboard.
3. **Close the browser tab before** the client unlock runs.
4. Wait ~30 seconds, refresh the report page.

- [ ] Report shows **full** tier (webhook applied unlock)
- [ ] `processed_webhook_payments.json` contains the payment id
- [ ] Flask log shows `Razorpay webhook handled`

---

## 12. Production checks

- [ ] HTTPS enabled; HSTS header present (non-dev)
- [ ] `APP_PASSWORD` or other access control configured if needed
- [ ] Live Razorpay keys + webhook secret (not test keys)
- [ ] Grievance Officer placeholders in Privacy Policy replaced before public launch
- [ ] `support@anixai.io` reachable

---

## Sign-off

| Role | Name | Date | Pass/Fail |
|------|------|------|-----------|
| Tester | | | |
| Owner | | | |
