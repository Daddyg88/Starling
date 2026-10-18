@echo off
rem Double-click, then do the thing that goes wrong in the game.
rem Press Ctrl+C to stop. Send me logs\debug_session.txt.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --debug
echo.
pause
