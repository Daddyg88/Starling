@echo off
rem Start STARLING WITH her ears on. Say her name, then your request. Ctrl+C to stop.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --listen
echo.
pause
