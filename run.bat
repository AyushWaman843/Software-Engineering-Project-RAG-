@echo off
REM Quick start for DPDP Compliance Scanner (Windows)

echo ========================================
echo DPDP Act Compliance Scanner
echo ========================================
echo.

if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo.
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

python -c "import flask" 2>nul
if errorlevel 1 (
    echo Installing Python dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
    echo.
)

if not exist ".env" (
    echo Tip: copy .env.example to .env and add DEEPSEEK_API_KEY
    echo.
)

if not exist "web\node_modules\" (
    echo Installing Node dependencies...
    call npm install --prefix web
    echo.
)

echo Starting dev servers (Next.js :3000 + Flask API :5000)...
echo Open http://localhost:3000
echo Press Ctrl+C to stop
echo.

npm run dev --prefix web

pause
