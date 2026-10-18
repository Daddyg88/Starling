@echo off
rem Double-click to record the buttons you press (for building macros). Presses nothing itself.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --record-buttons
echo.
pause
