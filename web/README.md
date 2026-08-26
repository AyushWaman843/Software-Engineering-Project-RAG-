# DPDP Compliance Scanner — Web App

Single React app (Next.js 15) for the DPDP compliance scanner.  
`npm run dev` starts **both** the UI and the Python scan engine automatically.

## Tech stack

| Component | Technology | Version |
|-----------|------------|---------|
| Web Framework | Next.js (App Router) | 15.1.0 |
| Language | TypeScript (strict) | 5.x |
| UI | React | 19.0.0 |
| CSS | Tailwind CSS | 3.4.17 |
| Animation | Framer Motion | 11.x |
| Icons | Lucide React | 0.469.0 |
| Scan engine | Python (Flask API, auto-started) | — |

## Quick start

From the **project root** or **`web/`** folder:

```powershell
cd c:\Users\palla\Downloads\dpdp_comp\web
npm install
npm run dev
```

Or from the repo root:

```powershell
npm install
npm run dev
```

Open **http://localhost:3000** — that is the only URL you need.

The dev script starts:
1. Python scan API on `127.0.0.1:5000` (internal — scraping, DeepSeek, PDF reports)
2. Next.js on `http://localhost:3000` (your app)

## First-time Python setup

```powershell
cd c:\Users\palla\Downloads\dpdp_comp
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Add DEEPSEEK_API_KEY to .env
```

## Environment

| File | Variable | Default |
|------|----------|---------|
| `web/.env.local` | `BACKEND_URL` | `http://127.0.0.1:5000` |
| shell | `SCANNER_API_PORT` | `5000` |

## Project layout

```
dpdp_comp/
├── app.py              # Python scan API (started automatically)
├── scan_runner.py      # Scan orchestration
├── web/                # Next.js React app ← you work here
│   ├── src/app/        # Pages & routes
│   └── scripts/dev.mjs # Starts API + Next.js
└── results/            # Saved scan JSON
```

PDF reports use `templates/pdf_assets/letterhead.png` (embedded by the Python report generator).
