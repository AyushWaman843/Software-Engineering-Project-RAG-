#!/bin/bash
# Quick start for DPDP Compliance Scanner (macOS/Linux)

set -e

echo "========================================"
echo "DPDP Act Compliance Scanner"
echo "========================================"
echo

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo
fi

echo "Activating virtual environment..."
source venv/bin/activate

if ! python -c "import flask" 2>/dev/null; then
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
    echo
fi

if [ ! -f ".env" ]; then
    echo "Tip: copy .env.example to .env and add DEEPSEEK_API_KEY"
    echo
fi

if [ ! -d "web/node_modules" ]; then
    echo "Installing Node dependencies..."
    npm install --prefix web
    echo
fi

echo "Starting dev servers (Next.js :3000 + Flask API :5000)..."
echo "Open http://localhost:3000"
echo "Press Ctrl+C to stop"
echo

npm run dev --prefix web
