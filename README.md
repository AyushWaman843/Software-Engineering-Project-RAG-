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

## Project layout

```
dpdp_comp/
├── app.py                 # Flask JSON API
├── scan_runner.py         # Scan orchestration & job state
├── llm_analyzer.py        # DeepSeek LLM analysis
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
| `APP_PASSWORD` | both | HTTP Basic Auth on the UI (optional) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | `.env` | Premium checkout (optional) |
| `RAZORPAY_WEBHOOK_SECRET` | `.env` | Razorpay webhook signature verification |

See **DEPLOY.md** for production (Docker, Gunicorn, security).

## Production

```bash
docker compose up --build
```

Or see DEPLOY.md for local production without Docker.

## Tests

```bash
pytest tests/
```

See **SMOKETEST.md** for the manual pre-launch checklist.

## Demo reset (clean slate)

```powershell
python scripts/reset_all_data.py
```

Or run `supabase/reset_all_data.sql` in the Supabase SQL Editor. See **DEPLOY.md** for details.
