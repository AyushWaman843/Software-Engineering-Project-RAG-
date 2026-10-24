# Engineering and operations

## Architecture and boundaries

Next.js serves the UI and forwards `/api/*` to Flask. Flask owns validation,
scan jobs, quotas, reports, and payment verification. Supabase owns identity,
durable report copies, and entitlement records. A request's `X-User-Id` is
metadata only; Flask verifies the Supabase bearer token before using an
identity. Trusted TrustStack calls need `X-TrustStack-Proxy: 1`, a valid bearer
token, and `X-Anix-Internal-Proxy` matching the server-only
`INTERNAL_PROXY_SECRET` on both services.

## Database rollout

On an existing database, apply `supabase/migrate_atomic_scan_slots.sql` after
the unified auth schema. For a new database, apply `supabase/schema.sql` and
the documented unified auth migration first. The new functions reserve,
refund, and grant free, Pilot, prepaid, and legacy Pro slots in database
transactions. Deploy the migration before the API code: missing functions
cause scan reservations and prepaid credit grants to fail closed. Keep the
Supabase service role key only on the server. Do not run reset SQL in
production.

## Data lifecycle

Completed scan jobs and legacy uploaded PDFs are removed after 30 days by a
daily sweep on active production API instances. New PDF uploads are extracted
in memory and their original files are not saved. Reports, including paid
reports and extracted policy text, remain available for the account lifetime;
Supabase mirrors them in case local disk is lost. Keep the report mirror and
its backups sized accordingly. The sweep is opportunistic: it runs on incoming
requests, so an idle service may purge late.

For a verified account deletion request, run
`python scripts/clear_user_data.py user@example.com --delete-account` from a
server with its Supabase service role key and access to the report volume.
Without `--delete-account`, it removes scanner data but keeps login. The
script removes local and Supabase scanner data; retain any payment records
required for accounting or disputes. Review output and retry if the network
fails. Backups and copies outside this deployment need their own deletion
process.

## Verification and incidents

Run `python -m pytest tests -q`, `npm run lint --prefix web`,
`npm run typecheck --prefix web`, and `npm run build --prefix web` before a
release. CI runs the same gates. Use the `X-Request-ID` response header to
find a request in API logs; logs record method, path, status, and duration.
Check `/health`, Supabase connectivity, pending scan jobs, and payment
webhook delivery during an incident. A failed scan refunds its reserved slot;
investigate any `Could not refund` log entry before changing balances.

## Limits requiring separate validation

Automated tests cover core boundary behavior but do not prove legal accuracy
of DPDP findings. Have a qualified reviewer check scoring rules and a curated
set of real policies before treating a score as legal advice. Run a manual
browser check of keyboard navigation, screen reader labels, payment and PDF
flows, and a production-like scan before launch. Paid integrations require
their own credentials and provider plans; this engineering work adds no new
paid service.
