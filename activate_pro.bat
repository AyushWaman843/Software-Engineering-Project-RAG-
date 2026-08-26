
@echo off
echo.
echo ========================================
echo   ACTIVATING PRO SUBSCRIPTION
echo ========================================
echo.

cd /d "%~dp0"
.\venv\Scripts\python.exe activate_pro_manual.py

echo.
pause
