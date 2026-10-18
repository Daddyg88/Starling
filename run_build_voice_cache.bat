@echo off
rem Double-click to pre-make every voice line (takes a few minutes, only needed once).
rem After this, her lines play instantly. Safe to run again any time.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --build-voice-cache
echo.
pause
