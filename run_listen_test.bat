@echo off
rem Double-click to test your microphone and what STARLING hears.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --listen-test
echo.
pause
