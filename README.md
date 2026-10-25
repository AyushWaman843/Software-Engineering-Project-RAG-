# DPDP Act Compliance Scanner

Evaluates website compliance with India's **Digital Personal Data Protection (DPDP) Act, 2025**.  
Next.js UI + Python Flask API with LLM-assisted analysis, PDF reports, and optional premium unlock (Razorpay).

## Quick start

```powershell
# One-time setup
python -m venv venv
.\venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # add DEEPSEEK_API_KEY, API_KEY, etc.
copy web\.env.local.example web\.env.local

cd web
npm install
npm run dev
```

Open **http://localhost:3000**. The dev script starts both:
- Next.js on `:3000` (UI)
- Flask API on `127.0.0.1:5000` (scan engine, internal)

From the repo root you can also run `npm install && npm run dev` (root `package.json` delegates to `web/`).

## Architecture

```
web/ (Next.js)  ──proxy /api/*──▶  app.py (Flask JSON API)
                                         │
                    scan_runner.py ◀─────┤ scraping, LLM, PDF
                    llm_analyzer.py      │
                    report_generator.py  └── results/, jobs/, uploads/
```

## RAG pipeline

1. `scraper.py` finds and extracts the privacy policy, terms and cookie pages.
2. `retrieval.py` splits each document into sentence-aligned chunks (source
   offsets kept), indexes them with BM25, and ranks chunks per DPDP indicator
   with hand-built query profiles. It is dependency-free; the nine indicators
   are a fixed rubric, so no embedding service is needed.
3. `llm_analyzer.py` sends documents up to `RAG_FULL_TEXT_MAX_CHARS` whole (by
   default 100,000 characters, the old hard cap, so what used to be sent whole
   still is). Longer ones are reduced to the passages retrieved for each
   indicator (plus each document's first and last chunk) instead of being
   silently truncated. Text that is not mostly English is always sent whole.
   The DPDP checklist stays a fixed system prompt.
4. The answer is then checked against the text. Quoted excerpts must exist in
   the source (tolerant of case, whitespace and quote style); the exact wording
   replaces a quote that was only approximately right. A "Found" with nothing in
   the text behind it is lowered to Missing, a missing quote is filled in from
   retrieved evidence when a sentence clearly qualifies, an unverified quote caps
   the confidence, and rule numbers that do not exist in the gazette
   (`rules_kb.py`) are corrected. Every adjustment is listed in
   `analysis_details.quality_flags`. The English-vocabulary checks are skipped
   for text that is not mostly English (flag `evidence_checks_skipped`).
5. Results are cached for 24 hours by content hash (policy, terms, cookie flag,
   model, prompt, retrieval settings), not by URL.
6. Paid scans below 80% average confidence fetch related same-site pages
   (grievance, DPO, rights, children, consent, contact) and re-run the analysis
   (`confidence_refinement.py`). This is a second LLM call for those scans; set
   `CONFIDENCE_REFINEMENT_ENABLED=0` to turn it off.

`analysis_details.retrieval`, `quality_flags` and `llm_usage` in each stored
report record what the model was shown, what the checks changed, and the tokens,
latency and attempts it took. They are left out of the JSON API responses.
Optional tuning, all with defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `RAG_FULL_TEXT_MAX_CHARS` | `100000` | Policy + terms up to this size are sent whole. Lower it (for example `40000`) to save tokens once retrieval has been validated with your model |
| `RAG_EVIDENCE_BUDGET_CHARS` | `24000` | Cap on retrieved evidence for longer documents |
| `RAG_TOP_K` | `4` | Chunks retrieved per indicator |
| `RAG_EVIDENCE_CHECKS` | `1` | `0` stops the evidence checks from changing statuses, confidences or excerpts |
| `CONFIDENCE_REFINEMENT_ENABLED` | `1` | `0` disables the paid-scan second pass (one fewer LLM call) |
| `DEEPSEEK_MAX_TOKENS` | `8192` | Output token budget for the analysis (the old code used 4096) |
| `DEEPSEEK_JSON_MODE` | `0` | `1` asks the API for JSON mode; off by default because DeepSeek documents that it can return empty content |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | Another OpenAI-compatible endpoint, if `api.deepseek.com` is blocked on your network |
| `LLM_CACHE_MAX_ENTRIES` | `256` | Size bound of the in-memory result cache |

### Measuring the pipeline

```powershell
python rag_eval.py                                  # retrieval recall and ranking on gold fixtures with realistic decoys
python rag_eval.py --pad 30000 --min-recall 0.95    # a longer document; exit code 1 below the bar
python rag_eval.py --live                           # also run the LLM on the first 2 fixtures (at most 2 real API calls)
python rag_eval.py --live --max-calls 4             # raise the limit on purpose
python rag_eval.py --inspect policy.txt             # what would be sent to the model for any policy text
```

Run it after changing prompts, retrieval profiles or thresholds. `--live` calls
the DeepSeek API and uses tokens, so it needs `DEEPSEEK_API_KEY`. It makes at
most `--max-calls` requests (default 2) in total, retries included, and stops
before the first one past the limit, so a run can never spend more. Each run
starts with an empty cache. The fixtures in
`tests/fixtures/rag_eval/` are synthetic and the labels are not legal advice: to
measure on real wording, add a policy as a `.txt` file plus an entry in
`cases.json`.

## Project layout

```
dpdp_comp/
├── app.py                 # Flask JSON API
├── scan_runner.py         # Scan orchestration & job state
├── llm_analyzer.py        # DeepSeek LLM analysis
├── retrieval.py           # Chunking, BM25 retrieval, excerpt location
├── rules_kb.py            # DPDP Rules knowledge base (rule lookup, citation checks)
├── rag_eval.py            # Retrieval/LLM evaluation and policy inspector
├── cache.py               # Content-keyed LLM result cache
├── report_generator.py    # HTML → PDF reports
├── compliance_checker.py  # Rule-based scoring
├── scraper.py             # Web scraping (requests + Selenium)
├── entitlements.py        # Premium access gating
├── razorpay_payments.py   # Payment checkout
├── templates/pdf_assets/  # Letterhead image for PDFs
├── dpdp_rules.txt         # DPDP rules reference for LLM
├── web/                   # Next.js frontend
├── tests/                 # pytest suite
├── results/               # Saved scan JSON (runtime)
├── jobs/                  # In-progress scan jobs (runtime)
└── uploads/               # Uploaded policy PDFs (runtime)
```

## Environment

Copy `.env.example` to `.env` (backend) and `web/.env.local.example` to `web/.env.local` (frontend).

| Variable | Where | Purpose |
|----------|-------|---------|
| `DEEPSEEK_API_KEY` | `.env` | LLM analysis |
| `API_KEY` | `.env` | Protects backend `/api/*` |
| `INTERNAL_API_KEY` | `web/.env.local` | Same value as `API_KEY`; injected by Next.js proxy |
| `INTERNAL_PROXY_SECRET` | both | Shared secret for trusted upstream TrustStack assertions; never expose in `NEXT_PUBLIC_*` |
| `APP_PASSWORD` | both | HTTP Basic Auth on the UI (optional) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | `.env` | Premium checkout (optional) |
| `RAZORPAY_WEBHOOK_SECRET` | `.env` | Razorpay webhook signature verification |

See **DEPLOY.md** for production (Docker, Gunicorn, security).

Apply `supabase/schema.sql`, the relevant unified-auth migration, then
`supabase/migrate_atomic_scan_slots.sql` before enabling scan quotas. The API
fails closed when the atomic quota functions are missing. Set the same
`INTERNAL_PROXY_SECRET` in the Flask and Next.js environments if TrustStack
forwards already-reserved scans.

## Production

```bash
docker compose up --build
```

Or see DEPLOY.md for local production without Docker.

## Tests

```bash
pytest tests/
cd web
npm run lint
npm run typecheck
npm run build
```

See **SMOKETEST.md** for the manual pre-launch checklist.

GitHub Actions runs these checks on pushes and pull requests. See
**ENGINEERING.md** for data retention, account deletion, quota behavior, and
operational checks.

## Demo reset (clean slate)

```powershell
python scripts/reset_all_data.py
```

Or run `supabase/reset_all_data.sql` in the Supabase SQL Editor. See **DEPLOY.md** for details.
